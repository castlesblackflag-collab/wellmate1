"""MemoryStore backed by the sage_user_profiles and sage_session_summaries tables."""

from engine.storage import run_db
from memory.store import MemoryStore, ProfileFact, SessionSummary, UserProfile


class SupabaseMemoryStore(MemoryStore):
    def __init__(self, client) -> None:
        self.db = client

    async def get_profile(self, user_id: str) -> UserProfile:
        res = await run_db(
            "read profile",
            lambda: self.db.table("sage_user_profiles").select("*").eq("user_id", user_id).limit(1).execute(),
        )
        if not res.data:
            return UserProfile(user_id=user_id)
        row = res.data[0]
        return UserProfile(user_id=user_id, facts=row.get("facts") or [], preferences=row.get("preferences") or {})

    async def _save(self, profile: UserProfile) -> UserProfile:
        row = {
            "user_id": profile.user_id,
            "facts": [f.model_dump(mode="json") for f in profile.facts],
            "preferences": profile.preferences,
        }
        await run_db("save profile", lambda: self.db.table("sage_user_profiles").upsert(row).execute())
        return profile

    async def upsert_fact(self, user_id: str, fact: ProfileFact) -> UserProfile:
        # Read-modify-write. Fine for one conversation at a time per user; if users ever run
        # parallel sessions, move this into a database function.
        profile = await self.get_profile(user_id)
        profile.facts = [f for f in profile.facts if f.key != fact.key] + [fact]
        return await self._save(profile)

    async def forget_fact(self, user_id: str, key: str) -> UserProfile:
        profile = await self.get_profile(user_id)
        profile.facts = [f for f in profile.facts if f.key != key]
        return await self._save(profile)

    async def add_summary(self, summary: SessionSummary) -> None:
        row = {
            "user_id": summary.user_id,
            "conversation_id": str(summary.conversation_id),
            "summary": summary.summary,
        }
        await run_db("save summary", lambda: self.db.table("sage_session_summaries").insert(row).execute())

    async def recent_summaries(self, user_id: str, limit: int = 5) -> list[SessionSummary]:
        res = await run_db(
            "read summaries",
            lambda: (
                self.db.table("sage_session_summaries")
                .select("user_id, conversation_id, summary, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            ),
        )
        return [SessionSummary.model_validate(r) for r in res.data]
