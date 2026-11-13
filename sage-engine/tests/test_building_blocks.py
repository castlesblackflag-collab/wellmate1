import asyncio
import uuid

import pytest
from pydantic import BaseModel, Field

from engine.model_adapter import FakeAdapter, get_adapter
from engine.types import ModelStop, TextDelta, ToolResult
from memory.store import InMemoryStore, ProfileFact, SessionSummary
from tests.conftest import make_settings
from tools.base import Tool, ToolContext, ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "Repeats text back."
    calls = 0

    class Input(BaseModel):
        text: str = Field(min_length=1, max_length=50)

    async def run(self, args, ctx):
        EchoTool.calls += 1
        return ToolResult(content=f"{ctx.user_id}: {args.text}")


class BrokenTool(Tool):
    name = "broken"
    description = "Always fails."

    class Input(BaseModel):
        pass

    async def run(self, args, ctx):
        raise RuntimeError("kaboom")


def _ctx():
    return ToolContext(user_id="u1", request_id="r1", settings=make_settings())


def test_tool_registry_validates_before_running():
    reg = ToolRegistry()
    reg.register(EchoTool())
    EchoTool.calls = 0

    ok = asyncio.run(reg.invoke("echo", {"text": "hi"}, _ctx()))
    assert ok.content == "u1: hi" and not ok.is_error

    bad = asyncio.run(reg.invoke("echo", {"text": ""}, _ctx()))
    assert bad.is_error and "text" in bad.content
    assert EchoTool.calls == 1  # the invalid call never reached run()


def test_tool_registry_handles_unknown_and_failing_tools(caplog):
    reg = ToolRegistry()
    reg.register(BrokenTool())
    assert asyncio.run(reg.invoke("missing", {}, _ctx())).is_error
    failed = asyncio.run(reg.invoke("broken", {}, _ctx()))
    assert failed.is_error and "kaboom" not in failed.content
    assert any("tool failed" in r.getMessage() for r in caplog.records)


def test_tool_names_are_unique_and_specs_have_schemas():
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError):
        reg.register(EchoTool())
    spec = reg.specs()[0]
    assert spec.name == "echo" and "text" in spec.input_schema["properties"]


def test_fake_adapter_streams_script_and_ends_with_stop():
    adapter = FakeAdapter(script=[TextDelta(text="a"), TextDelta(text="b"), ModelStop(reason="end_turn")])

    async def collect():
        return [e async for e in adapter.stream(system="s", messages=[])]

    events = asyncio.run(collect())
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "ab"
    assert isinstance(events[-1], ModelStop)


def test_adapter_factory():
    assert get_adapter("fake", "m").provider == "fake"
    assert get_adapter("claude", "claude-sonnet-5-5").model == "claude-sonnet-5-5"
    with pytest.raises(ValueError):
        get_adapter("llama", "x")


def test_memory_keeps_users_apart_and_replaces_facts():
    store = InMemoryStore()

    async def scenario():
        await store.upsert_fact("alice", ProfileFact(key="sleep_goal", value="7 hours"))
        await store.upsert_fact("alice", ProfileFact(key="sleep_goal", value="8 hours"))
        await store.upsert_fact("bob", ProfileFact(key="diet", value="vegetarian"))
        await store.add_summary(SessionSummary(user_id="alice", conversation_id=uuid.uuid4(), summary="talked sleep"))
        return (
            await store.get_profile("alice"),
            await store.get_profile("bob"),
            await store.recent_summaries("bob"),
            await store.forget_fact("alice", "sleep_goal"),
        )

    alice, bob, bob_summaries, alice_after = asyncio.run(scenario())
    assert [f.value for f in alice.facts] == ["8 hours"]
    assert [f.key for f in bob.facts] == ["diet"]
    assert bob_summaries == []
    assert alice_after.facts == []
