"""Conversations and their messages.

Every method that reads or writes a conversation takes the signed-in user's uid and filters
by it, so one user can never see or add to another's conversation. (The database also blocks
messages filed under the wrong user; see the migration.)
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from engine.storage import run_db
from engine.types import ChatMessage


def _now() -> datetime:
    return datetime.now(UTC)


class Conversation(BaseModel):
    id: uuid.UUID
    user_id: str
    title: str | None = None
    status: Literal["active", "closed"] = "active"
    chat_model: str | None = None
    engine_version: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    closed_at: datetime | None = None
    summarized_at: datetime | None = None


def trim_history(messages: list[ChatMessage]) -> list[ChatMessage]:
    """After cutting history to the last N messages, the window may start mid-exchange
    (a tool result whose request was cut off). Models reject that, so start at the first
    plain user message."""
    for i, msg in enumerate(messages):
        if msg.role == "user":
            return messages[i:]
    return []


class ConversationStore(ABC):
    @abstractmethod
    async def create(self, user_id: str, *, chat_model: str, engine_version: str) -> Conversation: ...

    @abstractmethod
    async def get(self, user_id: str, conversation_id: uuid.UUID) -> Conversation | None: ...

    @abstractmethod
    async def list_recent(self, user_id: str, limit: int = 20) -> list[Conversation]: ...

    @abstractmethod
    async def add_messages(self, user_id: str, conversation_id: uuid.UUID, messages: Sequence[ChatMessage]) -> None: ...

    @abstractmethod
    async def history(self, user_id: str, conversation_id: uuid.UUID, limit: int) -> list[ChatMessage]: ...

    @abstractmethod
    async def close(self, user_id: str, conversation_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def needing_summary(self, idle_since: datetime, limit: int = 50) -> list[Conversation]:
        """Conversations not yet summarized that are either closed or quiet since `idle_since`,
        across all users. Only the background job uses this."""

    @abstractmethod
    async def mark_summarized(self, user_id: str, conversation_id: uuid.UUID) -> None:
        """Records the summary is written and closes the conversation if it was still active."""


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self.conversations: dict[uuid.UUID, Conversation] = {}
        self.messages: dict[uuid.UUID, list[ChatMessage]] = {}

    async def create(self, user_id, *, chat_model, engine_version):
        conv = Conversation(id=uuid.uuid4(), user_id=user_id, chat_model=chat_model, engine_version=engine_version)
        self.conversations[conv.id] = conv
        self.messages[conv.id] = []
        return conv.model_copy()

    async def get(self, user_id, conversation_id):
        conv = self.conversations.get(conversation_id)
        return conv.model_copy() if conv and conv.user_id == user_id else None

    async def list_recent(self, user_id, limit=20):
        mine = [c for c in self.conversations.values() if c.user_id == user_id]
        return [c.model_copy() for c in sorted(mine, key=lambda c: c.updated_at, reverse=True)[:limit]]

    async def add_messages(self, user_id, conversation_id, messages):
        conv = self.conversations.get(conversation_id)
        if not conv or conv.user_id != user_id:
            raise PermissionError("conversation does not belong to this user")
        self.messages[conversation_id].extend(m.model_copy(deep=True) for m in messages)
        conv.updated_at = _now()

    async def history(self, user_id, conversation_id, limit):
        if not await self.get(user_id, conversation_id):
            return []
        return trim_history([m.model_copy(deep=True) for m in self.messages[conversation_id][-limit:]])

    async def close(self, user_id, conversation_id):
        conv = self.conversations.get(conversation_id)
        if conv and conv.user_id == user_id:
            conv.status, conv.closed_at = "closed", _now()

    async def needing_summary(self, idle_since, limit=50):
        due = [
            c
            for c in self.conversations.values()
            if c.summarized_at is None and (c.status == "closed" or c.updated_at < idle_since)
        ]
        return [c.model_copy() for c in sorted(due, key=lambda c: c.updated_at)[:limit]]

    async def mark_summarized(self, user_id, conversation_id):
        conv = self.conversations.get(conversation_id)
        if conv and conv.user_id == user_id:
            conv.summarized_at = _now()
            if conv.status == "active":
                conv.status, conv.closed_at = "closed", _now()


class SupabaseConversationStore(ConversationStore):
    def __init__(self, client) -> None:
        self.db = client

    async def create(self, user_id, *, chat_model, engine_version):
        row = {"user_id": user_id, "chat_model": chat_model, "engine_version": engine_version}
        res = await run_db("create conversation", lambda: self.db.table("sage_conversations").insert(row).execute())
        return Conversation.model_validate(res.data[0])

    async def get(self, user_id, conversation_id):
        res = await run_db(
            "get conversation",
            lambda: (
                self.db.table("sage_conversations")
                .select("*")
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            ),
        )
        return Conversation.model_validate(res.data[0]) if res.data else None

    async def list_recent(self, user_id, limit=20):
        res = await run_db(
            "list conversations",
            lambda: (
                self.db.table("sage_conversations")
                .select("*")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            ),
        )
        return [Conversation.model_validate(r) for r in res.data]

    async def add_messages(self, user_id, conversation_id, messages):
        if not messages:
            return
        rows = [
            {
                "conversation_id": str(conversation_id),
                "user_id": user_id,
                "role": m.role,
                "content": m.model_dump(mode="json"),
            }
            for m in messages
        ]
        await run_db("save messages", lambda: self.db.table("sage_messages").insert(rows).execute())
        # Bumps updated_at through the table's trigger, which the idle job relies on.
        await run_db(
            "touch conversation",
            lambda: (
                self.db.table("sage_conversations")
                .update({"status": "active"})
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .execute()
            ),
        )

    async def history(self, user_id, conversation_id, limit):
        res = await run_db(
            "load history",
            lambda: (
                self.db.table("sage_messages")
                .select("content, created_at")
                .eq("conversation_id", str(conversation_id))
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            ),
        )
        newest_first = [ChatMessage.model_validate(r["content"]) for r in res.data]
        return trim_history(list(reversed(newest_first)))

    async def close(self, user_id, conversation_id):
        await run_db(
            "close conversation",
            lambda: (
                self.db.table("sage_conversations")
                .update({"status": "closed", "closed_at": _now().isoformat()})
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .execute()
            ),
        )

    async def needing_summary(self, idle_since, limit=50):
        # Plain UTC with a Z: no "+" that could be misread inside the URL filter.
        cutoff = idle_since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        res = await run_db(
            "find conversations needing summary",
            lambda: (
                self.db.table("sage_conversations")
                .select("*")
                .is_("summarized_at", "null")
                .or_(f"status.eq.closed,updated_at.lt.{cutoff}")
                .order("updated_at")
                .limit(limit)
                .execute()
            ),
        )
        return [Conversation.model_validate(r) for r in res.data]

    async def mark_summarized(self, user_id, conversation_id):
        now = _now().isoformat()
        await run_db(
            "mark summarized",
            lambda: (
                self.db.table("sage_conversations")
                .update({"summarized_at": now})
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .execute()
            ),
        )
        await run_db(
            "close if still active",
            lambda: (
                self.db.table("sage_conversations")
                .update({"status": "closed", "closed_at": now})
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            ),
        )
