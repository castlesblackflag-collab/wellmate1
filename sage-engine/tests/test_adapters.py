import asyncio
from types import SimpleNamespace

import pytest
from google.genai import types

from engine.embeddings import FakeEmbedder, VertexEmbedder
from engine.errors import UpstreamError
from engine.model_adapter import (
    ClaudeVertexAdapter,
    GeminiVertexAdapter,
    to_claude_messages,
    to_gemini_contents,
)
from engine.types import ChatMessage, ModelStop, TextDelta, ToolCall, ToolResult, ToolSpec, ToolUseRequested

CONVO = [
    ChatMessage(role="user", text="How's my sleep?"),
    ChatMessage(
        role="assistant",
        text="Let me check.",
        tool_calls=[ToolCall(id="t1", name="a", arguments={"x": 1}), ToolCall(id="t2", name="b", arguments={})],
    ),
    ChatMessage(role="tool", tool_call_id="t1", tool_name="a", tool_result=ToolResult(content={"hours": 6})),
    ChatMessage(role="tool", tool_call_id="t2", tool_name="b", tool_result=ToolResult(content="oops", is_error=True)),
]
SPEC = ToolSpec(
    name="lookup",
    description="Looks up.",
    input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
)


async def collect(gen):
    return [e async for e in gen]


def test_claude_messages_group_tool_results():
    out = to_claude_messages(CONVO)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["type"] for b in out[1]["content"]] == ["text", "tool_use", "tool_use"]
    results = out[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert results[0]["content"] == '{"hours": 6}' and results[1]["is_error"] is True


class FakeClaudeStream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e

        return gen()

    async def get_final_message(self):
        return self.final


class FakeClaudeClient:
    def __init__(self, stream=None, error=None):
        self.kwargs, self._stream, self._error = None, stream, error
        self.messages = self

    def stream(self, **kwargs):
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return self._stream


def test_claude_adapter_streams_text_tools_and_usage():
    final = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hi"),
            SimpleNamespace(type="tool_use", id="t9", name="lookup", input={"q": "sleep"}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=80),
    )
    client = FakeClaudeClient(
        FakeClaudeStream([SimpleNamespace(type="text", text="Hi"), SimpleNamespace(type="other")], final)
    )
    adapter = ClaudeVertexAdapter("claude-test", "us-east5", "proj", client=client)

    events = asyncio.run(collect(adapter.stream(system="be kind", messages=CONVO[:1], tools=[SPEC], max_tokens=50)))

    assert isinstance(events[0], TextDelta) and events[0].text == "Hi"
    assert isinstance(events[1], ToolUseRequested) and events[1].call.arguments == {"q": "sleep"}
    stop = events[-1]
    assert isinstance(stop, ModelStop) and stop.reason == "tool_use"
    assert (stop.usage.input_tokens, stop.usage.output_tokens, stop.usage.cache_read_tokens) == (100, 20, 80)
    assert client.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert client.kwargs["tools"][0]["input_schema"] == SPEC.input_schema
    assert "temperature" not in client.kwargs


def test_claude_adapter_failure_becomes_upstream_error():
    adapter = ClaudeVertexAdapter("m", client=FakeClaudeClient(error=RuntimeError("quota")))
    with pytest.raises(UpstreamError, match="quota"):
        asyncio.run(collect(adapter.stream(system="s", messages=CONVO[:1])))


def test_gemini_contents_shape():
    contents = to_gemini_contents(CONVO)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[1].function_call.name == "a"
    responses = [p.function_response for p in contents[2].parts]
    assert [r.name for r in responses] == ["a", "b"]
    assert "error" in responses[1].response


def _chunk(parts, finish=None, usage=None):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)],
        usage_metadata=usage,
    )


class FakeGeminiClient:
    def __init__(self, chunks):
        self.chunks, self.kwargs = chunks, None
        self.aio = SimpleNamespace(models=self)

    async def generate_content_stream(self, **kwargs):
        self.kwargs = kwargs

        async def gen():
            for c in self.chunks:
                yield c

        return gen()


def test_gemini_adapter_streams_text_tools_and_usage():
    client = FakeGeminiClient(
        [
            _chunk([types.Part(text="Hel")]),
            _chunk([types.Part(text="lo")]),
            _chunk(
                [types.Part(function_call=types.FunctionCall(name="lookup", args={"q": "x"}))],
                finish=types.FinishReason.STOP,
                usage=types.GenerateContentResponseUsageMetadata(prompt_token_count=40, candidates_token_count=7),
            ),
        ]
    )
    adapter = GeminiVertexAdapter("gemini-test", "us-central1", "proj", client=client)
    events = asyncio.run(collect(adapter.stream(system="s", messages=CONVO, tools=[SPEC])))

    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello"
    call = next(e for e in events if isinstance(e, ToolUseRequested)).call
    assert call.name == "lookup" and call.id
    stop = events[-1]
    assert stop.reason == "tool_use" and stop.usage.input_tokens == 40 and stop.usage.output_tokens == 7
    config = client.kwargs["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].parameters_json_schema == SPEC.input_schema


def test_vertex_embedder_checks_vector_size():
    class Client:
        def __init__(self, dims):
            self.dims = dims
            self.aio = SimpleNamespace(models=self)

        async def embed_content(self, model, contents, config):
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * self.dims) for _ in contents])

    ok = VertexEmbedder("m", 768, "p", "r", client=Client(768))
    assert len(asyncio.run(ok.embed(["a", "b"], "query"))) == 2
    bad = VertexEmbedder("m", 768, "p", "r", client=Client(512))
    with pytest.raises(UpstreamError, match="512"):
        asyncio.run(bad.embed(["a"], "document"))


def test_fake_embedder_is_stable():
    e = FakeEmbedder(8)
    a, b = asyncio.run(e.embed(["same", "same"], "query"))
    assert a == b and len(a) == 8
