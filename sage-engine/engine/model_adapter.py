"""One interface in front of every model provider.

The rest of the engine only ever calls `adapter.stream(...)`. Swapping Claude for Gemini
(or running the bake-off) is a settings change, not a code change.

Status: the interface and a scripted fake for tests are ready. The Claude and Gemini
adapters are placeholders to be filled in when we build the agent loop (WS2).
Both will call Vertex AI using the Cloud Run service account, so neither needs an API key.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from engine.errors import NotBuiltYetError
from engine.types import ChatMessage, ModelEvent, ModelStop, TextDelta, ToolSpec


class ModelAdapter(ABC):
    provider: str

    def __init__(self, model: str, region: str | None = None):
        self.model = model
        self.region = region

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        max_tokens: int = 2048,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelEvent]:
        """Streams text deltas and tool-use requests, ending with exactly one ModelStop."""


class ClaudeVertexAdapter(ModelAdapter):
    provider = "claude"

    async def stream(self, **kwargs) -> AsyncIterator[ModelEvent]:  # pragma: no cover
        # Planned: anthropic SDK's AnthropicVertex client, messages.stream(), mapping
        # content_block_delta -> TextDelta and tool_use blocks -> ToolUseRequested.
        raise NotBuiltYetError("ClaudeVertexAdapter.stream is not implemented yet")
        yield  # makes this an async generator


class GeminiVertexAdapter(ModelAdapter):
    provider = "gemini"

    async def stream(self, **kwargs) -> AsyncIterator[ModelEvent]:  # pragma: no cover
        # Planned: google-genai SDK with vertexai=True, generate_content_stream().
        raise NotBuiltYetError("GeminiVertexAdapter.stream is not implemented yet")
        yield


class FakeAdapter(ModelAdapter):
    """Replays a scripted list of events. For tests and evals of the plumbing only."""

    provider = "fake"

    def __init__(self, model: str = "fake", region: str | None = None, script: list[ModelEvent] | None = None):
        super().__init__(model, region)
        self.script = script or [TextDelta(text="Hello from the fake model."), ModelStop(reason="end_turn")]
        self.calls: list[dict] = []

    async def stream(self, **kwargs) -> AsyncIterator[ModelEvent]:
        self.calls.append(kwargs)
        for event in self.script:
            yield event


_ADAPTERS: dict[str, type[ModelAdapter]] = {
    "claude": ClaudeVertexAdapter,
    "gemini": GeminiVertexAdapter,
    "fake": FakeAdapter,
}


def get_adapter(provider: str, model: str, region: str | None = None) -> ModelAdapter:
    try:
        cls = _ADAPTERS[provider]
    except KeyError:
        raise ValueError(f"Unknown model provider: {provider!r}") from None
    return cls(model, region)
