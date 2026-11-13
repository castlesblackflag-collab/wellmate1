"""The memory interface, plus an in-memory version for tests and evals.

Two kinds of memory:
- A profile: durable facts and preferences ("prefers short answers", "goal: sleep 7 hours").
- Session summaries: a short recap written by the background model when a conversation ends.

A Supabase-backed store (tables sage_user_profiles and sage_session_summaries) is the next
step, in WS4. Every method takes the user's uid and must never return another user's data.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileFact(BaseModel):
    key: str  # short stable label, e.g. "sleep_goal"
    value: str
    source: str = "conversation"  # where Sage learned it
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserProfile(BaseModel):
    user_id: str
    facts: list[ProfileFact] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    user_id: str
    conversation_id: UUID
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryStore(ABC):
    @abstractmethod
    async def get_profile(self, user_id: str) -> UserProfile: ...

    @abstractmethod
    async def upsert_fact(self, user_id: str, fact: ProfileFact) -> UserProfile: ...

    @abstractmethod
    async def forget_fact(self, user_id: str, key: str) -> UserProfile: ...

    @abstractmethod
    async def add_summary(self, summary: SessionSummary) -> None: ...

    @abstractmethod
    async def recent_summaries(self, user_id: str, limit: int = 5) -> list[SessionSummary]: ...


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._summaries: list[SessionSummary] = []

    async def get_profile(self, user_id: str) -> UserProfile:
        return self._profiles.get(user_id, UserProfile(user_id=user_id)).model_copy(deep=True)

    async def upsert_fact(self, user_id: str, fact: ProfileFact) -> UserProfile:
        profile = self._profiles.setdefault(user_id, UserProfile(user_id=user_id))
        profile.facts = [f for f in profile.facts if f.key != fact.key] + [fact]
        return profile.model_copy(deep=True)

    async def forget_fact(self, user_id: str, key: str) -> UserProfile:
        profile = self._profiles.setdefault(user_id, UserProfile(user_id=user_id))
        profile.facts = [f for f in profile.facts if f.key != key]
        return profile.model_copy(deep=True)

    async def add_summary(self, summary: SessionSummary) -> None:
        self._summaries.append(summary)

    async def recent_summaries(self, user_id: str, limit: int = 5) -> list[SessionSummary]:
        mine = [s for s in self._summaries if s.user_id == user_id]
        return sorted(mine, key=lambda s: s.created_at, reverse=True)[:limit]
