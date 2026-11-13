"""One interface in front of every model provider.

The rest of the engine only ever calls `adapter.stream(...)`. Swapping Claude for Gemini
(or running the bake-off) is a settings change, not a code change.

Both real adapters call Vertex AI with Google credentials: the Cloud Run service account in
production, your own `gcloud auth application-default login` locally. No API keys.
"""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Any

from engine.errors import UpstreamError
from engine.types import ChatMessage, ModelEvent, ModelStop, TextDelta, ToolCall, ToolSpec, ToolUseRequested, Usage

log = logging.getLogger("sage.model")


class ModelAdapter(ABC):
    provider: str

    def __init__(self, model: str, region: str | None = None, project: str | None = None):
        self.model = model
        self.region = region
        self.project = project

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelEvent]:
        """Streams text deltas and tool-use requests, ending with exactly one ModelStop."""


def _tool_result_text(msg: ChatMessage) -> str:
    result = msg.tool_result
    if result is None:
        return ""
    content = result.content
    return content if isinstance(content, str) else json.dumps(content, default=str)


# ---------------------------------------------------------------------------
# Claude on Vertex AI
# ---------------------------------------------------------------------------


def to_claude_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    """Converts our messages to Claude's format. Consecutive tool results are grouped into one
    user turn, which is what Claude expects after an assistant turn with several tool calls."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": _tool_result_text(msg),
                "is_error": bool(msg.tool_result and msg.tool_result.is_error),
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif msg.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.text:
                blocks.append({"type": "text", "text": msg.text})
            for call in msg.tool_calls:
                blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        else:
            out.append({"role": "user", "content": msg.text or ""})
    return out


_CLAUDE_STOP = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens", "refusal": "refusal"}


class ClaudeVertexAdapter(ModelAdapter):
    provider = "claude"

    def __init__(self, model: str, region: str | None = None, project: str | None = None, client: Any = None):
        super().__init__(model, region, project)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from anthropic import AsyncAnthropicVertex

            self._client = AsyncAnthropicVertex(project_id=self.project, region=self.region)
        return self._client

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelEvent]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            # The system prompt is marked cacheable: it's the same for every turn of a
            # conversation, so repeat turns are cheaper and faster.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": to_claude_messages(messages),
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools
            ]
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            async with self.client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if getattr(event, "type", None) == "text":
                        yield TextDelta(text=event.text)
                final = await stream.get_final_message()
        except Exception as exc:
            raise UpstreamError(f"Claude call failed: {type(exc).__name__}: {exc}") from exc

        for block in final.content:
            if getattr(block, "type", None) == "tool_use":
                yield ToolUseRequested(call=ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))

        usage = final.usage
        yield ModelStop(
            reason=_CLAUDE_STOP.get(final.stop_reason or "", "other"),
            usage=Usage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
        )


# ---------------------------------------------------------------------------
# Gemini on Vertex AI
# ---------------------------------------------------------------------------


def to_gemini_contents(messages: Sequence[ChatMessage]) -> list[Any]:
    from google.genai import types

    contents: list[types.Content] = []
    for msg in messages:
        if msg.role == "tool":
            response = {"result": _tool_result_text(msg)}
            if msg.tool_result and msg.tool_result.is_error:
                response = {"error": _tool_result_text(msg)}
            part = types.Part(
                function_response=types.FunctionResponse(id=msg.tool_call_id, name=msg.tool_name, response=response)
            )
            if contents and contents[-1].role == "user" and contents[-1].parts[0].function_response:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
        elif msg.role == "assistant":
            parts = []
            if msg.text:
                parts.append(types.Part(text=msg.text))
            for call in msg.tool_calls:
                parts.append(
                    types.Part(function_call=types.FunctionCall(id=call.id, name=call.name, args=call.arguments))
                )
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
        else:
            contents.append(types.Content(role="user", parts=[types.Part(text=msg.text or "")]))
    return contents


class GeminiVertexAdapter(ModelAdapter):
    provider = "gemini"

    def __init__(self, model: str, region: str | None = None, project: str | None = None, client: Any = None):
        super().__init__(model, region, project)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=self.project, location=self.region)
        return self._client

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 1500,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelEvent]:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            # We run tools ourselves so every call goes through validation and logging.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name, description=t.description, parameters_json_schema=t.input_schema
                        )
                        for t in tools
                    ]
                )
            ]
            if tools
            else None,
        )

        calls: list[ToolCall] = []
        usage = Usage()
        finish = None
        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model, contents=to_gemini_contents(messages), config=config
            )
            async for chunk in stream:
                candidate = (chunk.candidates or [None])[0]
                parts = (candidate.content.parts if candidate and candidate.content else None) or []
                for part in parts:
                    if part.text and not getattr(part, "thought", False):
                        yield TextDelta(text=part.text)
                    if part.function_call:
                        fc = part.function_call
                        calls.append(
                            ToolCall(id=fc.id or f"call_{len(calls)}", name=fc.name, arguments=dict(fc.args or {}))
                        )
                if candidate and candidate.finish_reason:
                    finish = str(candidate.finish_reason)
                if chunk.usage_metadata:
                    meta = chunk.usage_metadata
                    usage = Usage(
                        input_tokens=meta.prompt_token_count or 0,
                        output_tokens=meta.candidates_token_count or 0,
                        cache_read_tokens=meta.cached_content_token_count or 0,
                    )
        except Exception as exc:
            raise UpstreamError(f"Gemini call failed: {type(exc).__name__}: {exc}") from exc

        for call in calls:
            yield ToolUseRequested(call=call)
        if calls:
            reason = "tool_use"
        elif finish and "MAX_TOKENS" in finish:
            reason = "max_tokens"
        elif finish and ("SAFETY" in finish or "PROHIBITED" in finish):
            reason = "refusal"
        else:
            reason = "end_turn"
        yield ModelStop(reason=reason, usage=usage)


# ---------------------------------------------------------------------------
# Fake (tests and evals of the plumbing)
# ---------------------------------------------------------------------------


class FakeAdapter(ModelAdapter):
    """Replays scripted model output. Pass one list of events per model call; each call to
    stream() plays the next list. For tests and plumbing checks only."""

    provider = "fake"

    def __init__(
        self,
        model: str = "fake",
        region: str | None = None,
        project: str | None = None,
        script: list[ModelEvent] | None = None,
        rounds: list[list[ModelEvent]] | None = None,
    ):
        super().__init__(model, region, project)
        default = [TextDelta(text="Hello from the fake model."), ModelStop(reason="end_turn")]
        self.rounds = rounds or [script or default]
        self.calls: list[dict] = []

    async def stream(self, **kwargs) -> AsyncIterator[ModelEvent]:
        self.calls.append(kwargs)
        events = self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]
        for event in events:
            if isinstance(event, Exception):
                raise event
            yield event


_ADAPTERS: dict[str, type[ModelAdapter]] = {
    "claude": ClaudeVertexAdapter,
    "gemini": GeminiVertexAdapter,
    "fake": FakeAdapter,
}


def get_adapter(provider: str, model: str, region: str | None = None, project: str | None = None) -> ModelAdapter:
    try:
        cls = _ADAPTERS[provider]
    except KeyError:
        raise ValueError(f"Unknown model provider: {provider!r}") from None
    return cls(model, region, project)
