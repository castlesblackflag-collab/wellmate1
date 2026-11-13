"""One record per conversation turn: tokens, cost, timing, tools, safety level, errors.

This feeds the cost and quality dashboard (WS8). Logging a turn must never break the
conversation, so failures here are logged loudly but not raised.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, Field

from engine.storage import run_db
from engine.types import Usage

log = logging.getLogger("sage.turns")


class TurnRecord(BaseModel):
    conversation_id: uuid.UUID | None
    user_id: str
    request_id: str
    model: str
    usage: Usage = Field(default_factory=Usage)
    cost_usd: Decimal | None = None
    first_token_ms: int | None = None
    total_ms: int | None = None
    tools_used: list[str] = Field(default_factory=list)
    safety_level: str | None = None
    error_code: str | None = None


def compute_cost(model: str, usage: Usage, prices: dict[str, dict[str, float]]) -> Decimal | None:
    """USD cost from per-million-token prices. Returns None when the model has no price set,
    so the dashboard shows a gap rather than a made-up number."""
    p = prices.get(model)
    if not p:
        return None
    uncached_input = max(usage.input_tokens - usage.cache_read_tokens, 0)
    total = (
        Decimal(str(p.get("input", 0))) * uncached_input
        + Decimal(str(p.get("cache_read", p.get("input", 0)))) * usage.cache_read_tokens
        + Decimal(str(p.get("output", 0))) * usage.output_tokens
    ) / Decimal(1_000_000)
    return total.quantize(Decimal("0.000001"))


class TurnLogger(ABC):
    async def log(self, record: TurnRecord) -> None:
        try:
            await self._write(record)
        except Exception:
            log.exception("turn log write failed", extra={"request_id": record.request_id})

    @abstractmethod
    async def _write(self, record: TurnRecord) -> None: ...


class InMemoryTurnLogger(TurnLogger):
    def __init__(self) -> None:
        self.records: list[TurnRecord] = []

    async def _write(self, record):
        self.records.append(record)


class SupabaseTurnLogger(TurnLogger):
    def __init__(self, client) -> None:
        self.db = client

    async def _write(self, record):
        row = {
            "conversation_id": str(record.conversation_id) if record.conversation_id else None,
            "user_id": record.user_id,
            "request_id": record.request_id,
            "model": record.model,
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cost_usd": str(record.cost_usd) if record.cost_usd is not None else None,
            "first_token_ms": record.first_token_ms,
            "total_ms": record.total_ms,
            "tools_used": record.tools_used,
            "safety_level": record.safety_level,
            "error_code": record.error_code,
        }
        await run_db("write turn log", lambda: self.db.table("sage_turn_logs").insert(row).execute())
