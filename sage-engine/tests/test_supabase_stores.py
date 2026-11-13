"""The Supabase stores, checked against a fake client: every user-data query must filter by
the signed-in user, and rows must map cleanly to our models."""

import asyncio
import uuid

import pytest

from engine.conversations import SupabaseConversationStore
from engine.errors import UpstreamError
from engine.turn_log import SupabaseTurnLogger, TurnRecord
from engine.types import ChatMessage
from memory.store import ProfileFact
from memory.supabase_store import SupabaseMemoryStore
from tests.fakes import FakeSupabase

CID = uuid.uuid4()
CONV_ROW = {
    "id": str(CID),
    "user_id": "u1",
    "status": "active",
    "created_at": "2026-11-13T10:00:00+00:00",
    "updated_at": "2026-11-13T10:00:00+00:00",
}


def has_user_filter(query, uid="u1"):
    return ("eq", ("user_id", uid)) in query.filters()


def test_conversation_reads_and_writes_are_user_scoped():
    db = FakeSupabase(responses=[[CONV_ROW], [], [], []])
    store = SupabaseConversationStore(db)

    async def go():
        conv = await store.get("u1", CID)
        await store.add_messages("u1", CID, [ChatMessage(role="user", text="hi")])
        await store.close("u1", CID)
        return conv

    conv = asyncio.run(go())
    assert conv.id == CID
    for q in db.queries:
        if q.table != "sage_messages" or q.ops[0][0] != "insert":
            assert has_user_filter(q), q.table
    insert = db.queries[1]
    row = insert.ops[0][1][0][0]
    assert row["user_id"] == "u1" and row["content"]["text"] == "hi"


def test_history_is_oldest_first_and_trimmed():
    newest_first = [
        {"content": ChatMessage(role="assistant", text="2").model_dump(mode="json")},
        {"content": ChatMessage(role="user", text="1").model_dump(mode="json")},
        {"content": ChatMessage(role="tool", tool_call_id="x").model_dump(mode="json")},
    ]
    db = FakeSupabase(responses=[newest_first])
    msgs = asyncio.run(SupabaseConversationStore(db).history("u1", CID, 10))
    assert [m.text for m in msgs] == ["1", "2"]
    assert has_user_filter(db.queries[0])


def test_needing_summary_and_mark_summarized():
    from datetime import UTC, datetime

    db = FakeSupabase(responses=[[CONV_ROW], [], []])
    store = SupabaseConversationStore(db)
    found = asyncio.run(store.needing_summary(datetime(2026, 11, 13, tzinfo=UTC)))
    assert found[0].id == CID
    assert ("is_", ("summarized_at", "null")) in db.queries[0].filters()
    assert ("or_", ("status.eq.closed,updated_at.lt.2026-11-13T00:00:00Z",)) in db.queries[0].filters()
    asyncio.run(store.mark_summarized("u1", CID))
    assert all(has_user_filter(q) for q in db.queries[1:])


def test_memory_store_round_trip_is_user_scoped():
    db = FakeSupabase(responses=[[], []])
    profile = asyncio.run(SupabaseMemoryStore(db).upsert_fact("u1", ProfileFact(key="k", value="v")))
    assert [f.value for f in profile.facts] == ["v"]
    assert has_user_filter(db.queries[0])
    saved = db.queries[1].ops[0][1][0]
    assert saved["user_id"] == "u1" and saved["facts"][0]["key"] == "k"


def test_database_errors_become_upstream_errors():
    class Broken(FakeSupabase):
        def table(self, name):
            raise ConnectionError("network")

    with pytest.raises(UpstreamError, match="network"):
        asyncio.run(SupabaseMemoryStore(Broken()).get_profile("u1"))


def test_turn_log_failure_never_raises(caplog):
    class Broken(FakeSupabase):
        def table(self, name):
            raise ConnectionError("network")

    asyncio.run(
        SupabaseTurnLogger(Broken()).log(TurnRecord(conversation_id=None, user_id="u", request_id="r", model="m"))
    )
    assert any("turn log write failed" in r.getMessage() for r in caplog.records)
