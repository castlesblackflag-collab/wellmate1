"""Background work that runs outside a conversation, triggered by Cloud Scheduler.

close_idle_conversations: conversations that went quiet, or that the user closed, get a short
summary written by the background model (so Sage remembers them next time) and are marked done.
"""

import logging
from datetime import UTC, datetime, timedelta

from engine.conversations import ConversationStore
from engine.model_adapter import ModelAdapter
from engine.types import ChatMessage, TextDelta
from memory.store import MemoryStore, SessionSummary

log = logging.getLogger("sage.jobs")

SUMMARY_PROMPT = (
    "You write short private notes that help a health guide remember past conversations. "
    "Summarize the conversation below in 2 to 4 sentences: what the person wanted, anything "
    "they shared about their health, goals or circumstances, and anything left open to follow "
    "up on. Write plainly, in the third person. Leave out anything the person asked not to keep."
)


def transcript(messages: list[ChatMessage]) -> str:
    lines = []
    for m in messages:
        if m.role == "user" and m.text:
            lines.append(f"Person: {m.text}")
        elif m.role == "assistant" and m.text:
            lines.append(f"Guide: {m.text}")
    return "\n".join(lines)


async def summarize(model: ModelAdapter, messages: list[ChatMessage]) -> str:
    text = transcript(messages)
    if not text:
        return ""
    parts = []
    async for event in model.stream(
        system=SUMMARY_PROMPT, messages=[ChatMessage(role="user", text=text)], max_tokens=300
    ):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip()


async def close_idle_conversations(
    *,
    conversations: ConversationStore,
    memory: MemoryStore,
    model: ModelAdapter,
    idle_minutes: int,
    now: datetime | None = None,
    batch: int = 50,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    idle = await conversations.needing_summary(now - timedelta(minutes=idle_minutes), limit=batch)
    summarized = failed = 0
    for conv in idle:
        try:
            history = await conversations.history(conv.user_id, conv.id, limit=200)
            summary = await summarize(model, history)
            if summary:
                await memory.add_summary(SessionSummary(user_id=conv.user_id, conversation_id=conv.id, summary=summary))
                summarized += 1
            await conversations.mark_summarized(conv.user_id, conv.id)
        except Exception:
            # One bad conversation shouldn't stop the rest; it stays active and is retried next run.
            failed += 1
            log.exception("closing conversation failed", extra={"conversation_id": str(conv.id)})
    result = {"checked": len(idle), "summarized": summarized, "failed": failed}
    log.info("close_idle_conversations finished", extra=result)
    return result
