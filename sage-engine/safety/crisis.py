"""The crisis screen interface.

Every user message passes through a CrisisScreen before the model sees it. This is one of
our three hard rails: catching someone in crisis must not depend on how a prompt is worded.

Planned design (WS5): a fast rule-based check for clear signals, plus a flag from the model
for subtler ones, with a fixed escalation response and region-appropriate resources.

There is deliberately no default implementation here. A placeholder that always answered
"no concern" could end up wired in by accident, and that's the one mistake this part of the
system can't afford. Until the real screen exists, the chat endpoint stays switched off.
"""

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    NONE = "none"
    CONCERN = "concern"  # worth a gentle check-in, conversation continues normally
    CRISIS = "crisis"  # escalation response and resources come first


class ScreenResult(BaseModel):
    level: RiskLevel
    reasons: list[str] = Field(default_factory=list)  # for logs and evals, never shown to the user
    screener: str  # which check made the call, e.g. "rules" or "model"


class CrisisScreen(ABC):
    @abstractmethod
    async def screen(self, user_id: str, text: str) -> ScreenResult: ...
