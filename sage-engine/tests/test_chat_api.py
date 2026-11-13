import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import engine.job_auth as job_auth
from engine.agent import Sage
from engine.container import get_background_model, get_conversation_store, get_memory_store, get_sage
from engine.context import ContextBuilder, NoAgeWellSource
from engine.conversations import InMemoryConversationStore
from engine.jobs import close_idle_conversations, transcript
from engine.model_adapter import FakeAdapter
from engine.turn_log import InMemoryTurnLogger
from engine.types import ChatMessage, ModelStop, TextDelta
from memory.store import InMemoryStore
from tests.fakes import ClearScreen, parse_sse
from tools.base import ToolRegistry

JOB_SETTINGS = {
    "job_audience": "https://sage.example",
    "job_invoker_email": "scheduler@wellmate-i.iam.gserviceaccount.com",
}


def wire(client, *, model=None, store=None, memory=None):
    store = store or InMemoryConversationStore()
    memory = memory or InMemoryStore()
    settings = client.app.state.settings
    sage = Sage(
        settings=settings,
        model=model or FakeAdapter(model="claude-test"),
        tools=ToolRegistry(),
        conversations=store,
        context=ContextBuilder(persona="You are Sage.", memory=memory, agewell=NoAgeWellSource()),
        screen=ClearScreen(),
        turn_logger=InMemoryTurnLogger(),
    )
    o = client.app.dependency_overrides
    o[get_sage] = lambda: sage
    o[get_conversation_store] = lambda: store
    o[get_memory_store] = lambda: memory
    o[get_background_model] = lambda: FakeAdapter(
        script=[TextDelta(text="They asked about sleep."), ModelStop(reason="end_turn")]
    )
    return sage, store, memory


def test_chat_stays_off_when_enabled_but_no_crisis_screen(client_factory):
    r = client_factory(auth_disabled=True, chat_enabled=True).post("/v1/chat", json={"message": "hi"})
    assert r.status_code == 501


def test_chat_streams_server_sent_events(client_factory):
    client = client_factory(auth_disabled=True)
    wire(client)
    r = client.post("/v1/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["conversation", "text", "done"]
    assert events[-1][1]["request_id"] == r.headers["X-Request-ID"]

    conv_id = events[0][1]["conversation_id"]
    r2 = client.post("/v1/chat", json={"message": "again", "conversation_id": conv_id})
    assert parse_sse(r2.text)[0][1]["conversation_id"] == conv_id


def test_chat_unknown_conversation_is_plain_404(client_factory):
    client = client_factory(auth_disabled=True)
    wire(client)
    r = client.post("/v1/chat", json={"message": "hi", "conversation_id": str(uuid.uuid4())})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_conversation_endpoints(client_factory):
    client = client_factory(auth_disabled=True)
    _, store, _ = wire(client)
    conv_id = parse_sse(client.post("/v1/chat", json={"message": "hello there"}).text)[0][1]["conversation_id"]

    listed = client.get("/v1/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [conv_id]

    detail = client.get(f"/v1/conversations/{conv_id}").json()
    assert detail["messages"] == [
        {"role": "user", "text": "hello there"},
        {"role": "assistant", "text": "Hello from the fake model."},
    ]

    assert client.post(f"/v1/conversations/{conv_id}/close").json() == {"closed": True}
    assert store.conversations[uuid.UUID(conv_id)].status == "closed"
    assert client.get(f"/v1/conversations/{uuid.uuid4()}").status_code == 404


def test_conversations_belong_to_their_user(client_factory, monkeypatch):
    import engine.auth as auth

    client = client_factory()
    _, store, _ = wire(client)
    monkeypatch.setattr(auth, "verify_firebase_token", lambda token, pid: {"uid": token})
    conv_id = parse_sse(
        client.post("/v1/chat", json={"message": "mine"}, headers={"Authorization": "Bearer alice"}).text
    )[0][1]["conversation_id"]

    as_bob = {"Authorization": "Bearer bob"}
    assert client.get(f"/v1/conversations/{conv_id}", headers=as_bob).status_code == 404
    assert client.get("/v1/conversations", headers=as_bob).json()["conversations"] == []
    assert client.post("/v1/chat", json={"message": "x", "conversation_id": conv_id}, headers=as_bob).status_code == 404


def test_job_endpoint_needs_configuration_and_a_valid_caller(client_factory, monkeypatch):
    assert client_factory().post("/internal/jobs/close-idle").status_code == 503

    client = client_factory(**JOB_SETTINGS)
    wire(client)
    assert client.post("/internal/jobs/close-idle").status_code == 401

    monkeypatch.setattr(
        job_auth, "verify_google_token", lambda t, a: {"email": "someone@else.com", "email_verified": True}
    )
    assert client.post("/internal/jobs/close-idle", headers={"Authorization": "Bearer x"}).status_code == 401

    monkeypatch.setattr(
        job_auth,
        "verify_google_token",
        lambda t, a: {"email": JOB_SETTINGS["job_invoker_email"], "email_verified": True},
    )
    r = client.post("/internal/jobs/close-idle", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200 and r.json() == {"checked": 0, "summarized": 0, "failed": 0}


def test_close_idle_summarizes_quiet_and_closed_conversations():
    store, memory = InMemoryConversationStore(), InMemoryStore()
    model = FakeAdapter(script=[TextDelta(text="Talked about sleep."), ModelStop(reason="end_turn")])
    now = datetime.now(UTC)

    async def scenario():
        quiet = await store.create("u1", chat_model="m", engine_version="v")
        closed = await store.create("u2", chat_model="m", engine_version="v")
        fresh = await store.create("u3", chat_model="m", engine_version="v")
        for conv in (quiet, closed, fresh):
            await store.add_messages(
                conv.user_id,
                conv.id,
                [ChatMessage(role="user", text="hi"), ChatMessage(role="assistant", text="hello")],
            )
        store.conversations[quiet.id].updated_at = now - timedelta(hours=2)
        await store.close("u2", closed.id)
        result = await close_idle_conversations(
            conversations=store, memory=memory, model=model, idle_minutes=30, now=now
        )
        again = await close_idle_conversations(
            conversations=store, memory=memory, model=model, idle_minutes=30, now=now
        )
        return quiet, closed, fresh, result, again

    quiet, closed, fresh, result, again = asyncio.run(scenario())
    assert result == {"checked": 2, "summarized": 2, "failed": 0}
    assert again["checked"] == 0  # nothing is summarized twice
    assert store.conversations[quiet.id].status == "closed"
    assert store.conversations[fresh.id].status == "active"
    assert asyncio.run(memory.recent_summaries("u1"))[0].summary == "Talked about sleep."
    assert asyncio.run(memory.recent_summaries("u3")) == []


def test_close_idle_keeps_going_after_one_failure(caplog):
    class FlakyStore(InMemoryConversationStore):
        async def history(self, user_id, conversation_id, limit):
            if user_id == "bad":
                raise RuntimeError("boom")
            return await super().history(user_id, conversation_id, limit)

    store, memory = FlakyStore(), InMemoryStore()
    model = FakeAdapter(script=[TextDelta(text="ok"), ModelStop(reason="end_turn")])

    async def scenario():
        for uid in ("bad", "good"):
            c = await store.create(uid, chat_model="m", engine_version="v")
            await store.add_messages(uid, c.id, [ChatMessage(role="user", text="hi")])
            await store.close(uid, c.id)
        return await close_idle_conversations(conversations=store, memory=memory, model=model, idle_minutes=30)

    assert asyncio.run(scenario()) == {"checked": 2, "summarized": 1, "failed": 1}
    assert any("closing conversation failed" in r.getMessage() for r in caplog.records)


def test_transcript_skips_tool_traffic():
    msgs = [
        ChatMessage(role="user", text="a"),
        ChatMessage(role="tool", tool_call_id="t"),
        ChatMessage(role="assistant", text="b"),
    ]
    assert transcript(msgs) == "Person: a\nGuide: b"
