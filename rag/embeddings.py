"""Embedding backends for the RAG layer.

`VertexEmbedder` is the production backend — Vertex AI `text-embedding-004`,
768 dimensions, auth via ADC. The Vertex SDK is synchronous so we run calls in
a thread pool.

`HashEmbedder` is a deterministic 768-dim fake used in tests: the same text
always maps to the same vector, similar strings cluster, and no network access
is required. Never ship this to production — it's strictly for offline tests.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
from typing import Protocol

VERTEX_MODEL = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
VERTEX_DIM = 768


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class VertexEmbedder:
    """Thin async wrapper over `vertexai.language_models.TextEmbeddingModel`."""

    dim: int = VERTEX_DIM

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        model_name: str = VERTEX_MODEL,
    ):
        self._project = project or os.getenv("GCP_PROJECT_ID")
        self._location = location or os.getenv("GCP_REGION", "us-central1")
        self._model_name = model_name
        self._model = None  # lazy

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        if self._project:
            vertexai.init(project=self._project, location=self._location)
        self._model = TextEmbeddingModel.from_pretrained(self._model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()

        def _call() -> list[list[float]]:
            embeddings = model.get_embeddings(texts)
            return [e.values for e in embeddings]

        return await asyncio.to_thread(_call)


class HashEmbedder:
    """Deterministic 768-d pseudo-embedding for offline tests.

    Splits the input into tokens, hashes each to a bucket in [0, dim), and
    accumulates a bag-of-hashes vector. Identical strings produce identical
    vectors; strings that share tokens will be closer under cosine similarity.
    """

    def __init__(self, *, dim: int = VERTEX_DIM):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokenize(text):
            idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        # L2-normalize so cosine similarity behaves.
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


_TOKEN_SPLIT = __import__("re").compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on any non-alphanum. Keeps `aha_moment` and `aha-moment`
    tokenizing to ['aha','moment'] so underscored signal types match hyphenated
    playbook prose."""
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if t]
