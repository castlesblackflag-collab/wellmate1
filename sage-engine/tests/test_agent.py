import asyncio
import uuid
from decimal import Decimal

import pytest

from engine.agent import Sage
from engine.context import ContextBuilder, NoAgeWellSource
from engine.conversations import InMemoryConversationStore, trim_history
from engine.errors import NotFoundError, UpstreamError
from engine.model_adapter import FakeAdapter
from engine.persona import load_persona, parse_persona
from engine.turn_log import InMemoryTurnLogger, compute_cost
from engine.types import ChatMessage, ModelStop, TextDelta, ToolCall, ToolResult, ToolUseRequested, Usage
from memory.store import InMemoryStore, ProfileFact
from safety.crisis import RiskLevel, ScreenResult
from tests.conftest import make_settings
from tests.fakes import AlwaysCrisis, ClearScreen, LookupTool
from tools.base import ToolRegistry

TOOL_ROUND = [
    TextDelta(text="Let me look. "),
    ToolUseRequested(call=ToolCall(id="c1", name="lookup", arguments={"query": "sleep"})),
    ModelStop(reason="tool_use", usage=Usage(input_tokens=100, output_tokens=10)),
]
ANSWER_ROUND = [
    TextDelta(text="Here's what I found."),
    ModelStop(reason="end_turn", usage=Usage(input_tokens=150, output_tokens=20)),
]


def build(rounds=None, screen=None, memory=None, **settings):
    s = make_settings(**settings)
    registry = ToolRegistry()
    registry.register(LookupTool())
    memory = memory or InMemoryStore()
    sage = Sage(
        settings=s,
        model=FakeAdapter(model="claude-test", rounds=rounds or [ANSWER_ROUND]),
        tools=registry,
        conversations=InMemoryConversationStore(),
        context=ContextBuilder(persona="You are Sage.", memory=memory, agewell=NoAgeWellSource()),
        screen=screen or ClearScreen(),
        turn_logger=InMemoryTurnLogger(),
    )
    return sage


def run(sage, message="hi", user="u1", conversation_id=None):
    async def go():
        conv = await sage.open_conversation(user, conversation_id)
        events = [e async for e in sage.run_turn(user_id=user, conversation=conv, message=message, request_id="r1")]
        return conv, events

    return asyncio.run(go())


def kinds(events):
    return [e.event for e in events]


def test_plain_reply_is_streamed_saved_and_logged():
    sage = build()
    conv, events = run(sage)
    assert kinds(events) == ["conversation", "text", "done"]
    saved = sage.conversations.messages[conv.id]
    assert [m.role for m in saved] == ["user", "assistant"]
    assert saved[1].text == "Here's what I found."
    record = sage.turn_logger.records[0]
    assert record.usage.output_tokens == 20 and record.safety_level == "none" and record.error_code is None
    assert record.first_token_ms is not None


def test_tool_round_trip_with_citations():
    sage = build(rounds=[TOOL_ROUND, ANSWER_ROUND])
    conv, events = run(sage)
    assert kinds(events) == ["conversation", "text", "activity", "text", "citations", "done"]
    assert events[2].data["label"] == "Checking the research"
    assert events[4].data["items"][0]["identifier"] == "PMID:1"

    second_call = sage.model.calls[1]["messages"]
    assert second_call[-1].role == "tool" and second_call[-1].tool_result.content == "Findings about sleep"
    assert [m.role for m in sage.conversations.messages[conv.id]] == ["user", "assistant", "tool", "assistant"]
    record = sage.turn_logger.records[0]
    assert record.tools_used == ["lookup"] and record.usage.input_tokens == 250


def test_tool_rounds_are_capped_and_last_round_has_no_tools():
    sage = build(rounds=[TOOL_ROUND], max_tool_rounds=2)
    run(sage)
    assert len(sage.model.calls) == 3
    assert [len(c["tools"]) for c in sage.model.calls] == [1, 1, 0]


def test_invalid_tool_arguments_go_back_to_model_not_to_tool():
    bad = [ToolUseRequested(call=ToolCall(id="c1", name="lookup", arguments={})), ModelStop(reason="tool_use")]
    sage = build(rounds=[bad, ANSWER_ROUND])
    run(sage)
    tool_msg = sage.model.calls[1]["messages"][-1]
    assert tool_msg.tool_result.is_error and "query" in tool_msg.tool_result.content


def test_crisis_screen_answers_without_the_model():
    sage = build(screen=AlwaysCrisis())
    conv, events = run(sage)
    assert kinds(events) == ["conversation", "safety", "text", "done"]
    assert events[1].data["resources"][0]["name"] == "Test line"
    assert sage.model.calls == []
    assert sage.turn_logger.records[0].safety_level == "crisis"
    assert sage.conversations.messages[conv.id][-1].text.startswith("I'm really glad")


def test_concern_adds_a_note_to_the_system_prompt():
    sage = build(screen=ClearScreen(RiskLevel.CONCERN))
    run(sage)
    assert "safety check" in sage.model.calls[0]["system"]


def test_model_failure_becomes_error_event_and_is_logged():
    sage = build(rounds=[[TextDelta(text="Part"), UpstreamError("vertex down")]])
    _, events = run(sage)
    assert kinds(events) == ["conversation", "text", "error"]
    assert events[-1].data["error"]["code"] == "upstream_error"
    assert sage.turn_logger.records[0].error_code == "upstream_error"


def test_unexpected_failure_is_contained():
    sage = build(rounds=[[RuntimeError("bug")]])
    _, events = run(sage)
    assert events[-1].data["error"]["code"] == "internal_error"
    assert "bug" not in str(events[-1].data)


def test_other_users_conversation_is_not_found():
    sage = build()
    conv, _ = run(sage, user="alice")
    with pytest.raises(NotFoundError):
        run(sage, user="mallory", conversation_id=conv.id)


def test_conversation_continues_with_history():
    sage = build()
    conv, _ = run(sage, message="first")
    run(sage, message="second", conversation_id=conv.id)
    sent = sage.model.calls[1]["messages"]
    assert [m.text for m in sent if m.role == "user"] == ["first", "second"]


def test_profile_reaches_system_prompt_framed_as_data():
    memory = InMemoryStore()
    asyncio.run(memory.upsert_fact("u1", ProfileFact(key="sleep_goal", value="7 hours")))
    sage = build(memory=memory)
    run(sage)
    system = sage.model.calls[0]["system"]
    assert "sleep_goal: 7 hours" in system and "not instructions" in system


def test_memory_outage_does_not_stop_the_turn(caplog):
    class BrokenMemory(InMemoryStore):
        async def get_profile(self, user_id):
            raise UpstreamError("supabase down")

    sage = build(memory=BrokenMemory())
    _, events = run(sage)
    assert kinds(events)[-1] == "done"
    assert "couldn't be loaded" in sage.model.calls[0]["system"]
    assert any("context source failed" in r.getMessage() for r in caplog.records)


def test_trim_history_starts_at_a_user_message():
    msgs = [
        ChatMessage(role="tool", tool_call_id="x", tool_result=ToolResult(content="")),
        ChatMessage(role="assistant", text="..."),
        ChatMessage(role="user", text="hi"),
    ]
    assert [m.role for m in trim_history(msgs)] == ["user"]


def test_cost_uses_prices_and_cache_rate():
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=500_000)
    prices = {"m": {"input": 3.0, "output": 15.0, "cache_read": 0.3}}
    assert compute_cost("m", usage, prices) == Decimal("3.150000")
    assert compute_cost("unpriced", usage, prices) is None


def test_persona_file_loads_and_parses():
    assert "Who Sage is" in load_persona()
    assert parse_persona("notes\n---\nbody") == "body"
    with pytest.raises(ValueError):
        parse_persona("no separator")


def test_screen_result_defaults():
    r = ScreenResult(level=RiskLevel.NONE, screener="x")
    assert r.response_text is None and r.resources == []


def test_unused_uuid_is_not_found():
    with pytest.raises(NotFoundError):
        run(build(), conversation_id=uuid.uuid4())
