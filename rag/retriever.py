"""High-level RAG retrieval: embed a query and fetch the top-k chunks.

Agents depend on the `Retriever` interface, not the underlying store — that way
unit tests swap in an `InMemoryVectorStore` + `HashEmbedder` and still exercise
the same code path the production lifecycle agent uses.
"""
from __future__ import annotations

from opentelemetry import trace

from rag.embeddings import Embedder
from rag.schemas import SearchResult
from rag.store import VectorStore

_tracer = trace.get_tracer("rag.retriever")


class Retriever:
    def __init__(self, embedder: Embedder, store: VectorStore):
        if embedder.dim != store.dim:
            raise ValueError(
                f"embedder dim {embedder.dim} must match store dim {store.dim}"
            )
        self._embedder = embedder
        self._store = store

    async def retrieve(self, query: str, k: int = 3) -> list[SearchResult]:
        with _tracer.start_as_current_span("rag.retrieve") as span:
            span.set_attribute("rag.query.length", len(query))
            span.set_attribute("rag.k", k)
            [vec] = await self._embedder.embed([query])
            results = await self._store.search(vec, k=k)
            span.set_attribute("rag.hits", len(results))
            span.set_attribute(
                "rag.top_playbooks",
                [r.chunk.playbook_slug for r in results],
            )
            return results
