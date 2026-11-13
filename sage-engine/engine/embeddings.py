"""Turns text into vectors for knowledge search (WS3).

The vector size must match `sage_knowledge_chunks.embedding` (768 today). Documents and
search queries are embedded slightly differently ("task type"), which improves matching.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Literal

from engine.errors import UpstreamError

Task = Literal["document", "query"]


class Embedder(ABC):
    dimensions: int

    @abstractmethod
    async def embed(self, texts: Sequence[str], task: Task) -> list[list[float]]: ...


class VertexEmbedder(Embedder):
    def __init__(self, model: str, dimensions: int, project: str, region: str, client: Any = None):
        self.model = model
        self.dimensions = dimensions
        self.project = project
        self.region = region
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=self.project, location=self.region)
        return self._client

    async def embed(self, texts: Sequence[str], task: Task) -> list[list[float]]:
        from google.genai import types

        if not texts:
            return []
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY",
            output_dimensionality=self.dimensions,
        )
        try:
            result = await self.client.aio.models.embed_content(model=self.model, contents=list(texts), config=config)
        except Exception as exc:
            raise UpstreamError(f"Embedding call failed: {type(exc).__name__}: {exc}") from exc

        vectors = [list(e.values) for e in result.embeddings]
        bad = [len(v) for v in vectors if len(v) != self.dimensions]
        if bad:
            raise UpstreamError(f"Embedding size {bad[0]} does not match expected {self.dimensions}")
        return vectors


class FakeEmbedder(Embedder):
    """Deterministic vectors for tests: same text, same vector."""

    def __init__(self, dimensions: int = 768):
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str], task: Task) -> list[list[float]]:
        import hashlib

        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            out.append([(digest[i % len(digest)] - 128) / 128 for i in range(self.dimensions)])
        return out
