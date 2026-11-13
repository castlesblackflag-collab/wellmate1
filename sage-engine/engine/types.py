"""Shared shapes for conversations, tool calls and model output.

These are model-neutral on purpose: the model adapter translates between these and each
provider's own format, so nothing else in the engine cares whether Claude or Gemini answered.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str
    url: str | None = None
    source_type: Literal["pubmed", "web", "corpus", "curated", "internal"]
    identifier: str | None = None  # e.g. PMID, DOI, corpus row ID


class ToolSpec(BaseModel):
    """What the model is told about a tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    content: Any
    citations: list[Citation] = Field(default_factory=list)
    is_error: bool = False


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # set when role == "tool"
    tool_result: ToolResult | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


# Events a model adapter streams back during one model call.
class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolUseRequested(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    call: ToolCall


class ModelStop(BaseModel):
    type: Literal["stop"] = "stop"
    reason: Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]
    usage: Usage = Field(default_factory=Usage)


ModelEvent = TextDelta | ToolUseRequested | ModelStop
