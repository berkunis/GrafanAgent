"""Vector stores for the RAG layer.

`PgVectorStore` is the production store — asyncpg connection pool + the
`pgvector` extension on Cloud SQL (or Docker Postgres locally). Cosine
similarity via the `<=>` operator.

`InMemoryVectorStore` is the offline fallback: a Python list, numpy cosine,
deterministic. Unit tests and CI without Postgres both use this.
"""
from __future__ import annotations

import os
from typing import Any, Protocol

import numpy as np

from rag.schemas import Chunk, SearchResult


class VectorStore(Protocol):
    dim: int

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        ...

    async def search(self, query_embedding: list[float], k: int = 3) -> list[SearchResult]:
        ...

    async def count(self) -> int:
        ...


class InMemoryVectorStore:
    """Python-native store used by unit tests + `HashEmbedder`-backed dev flows."""

    def __init__(self, *, dim: int):
        self.dim = dim
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        for chunk, emb in zip(chunks, embeddings):
            if len(emb) != self.dim:
                raise ValueError(f"embedding dim {len(emb)} != store dim {self.dim}")
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = np.asarray(emb, dtype=np.float32)

    async def search(self, query_embedding: list[float], k: int = 3) -> list[SearchResult]:
        if not self._vectors:
            return []
        q = np.asarray(query_embedding, dtype=np.float32)
        q_norm = float(np.linalg.norm(q)) or 1.0
        scored: list[SearchResult] = []
        for chunk_id, vec in self._vectors.items():
            v_norm = float(np.linalg.norm(vec)) or 1.0
            score = float(np.dot(q, vec) / (q_norm * v_norm))
            scored.append(SearchResult(chunk=self._chunks[chunk_id], score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    async def count(self) -> int:
        return len(self._chunks)


DEFAULT_TABLE = "playbook_chunks"


class PgVectorStore:
    """Async Postgres/pgvector store. `dim` must match the column definition."""

    def __init__(
        self,
        *,
        dim: int,
        dsn: str | None = None,
        table: str = DEFAULT_TABLE,
    ):
        self.dim = dim
        self._dsn = dsn or os.environ["PGVECTOR_DSN"]
        self._table = table
        self._pool = None

    async def _pool_get(self):
        if self._pool is None:
            import asyncpg
            from pgvector.asyncpg import register_vector

            async def _init(conn):
                await register_vector(conn)

            self._pool = await asyncpg.create_pool(dsn=self._dsn, init=_init, min_size=1, max_size=4)
        return self._pool

    async def init_schema(self) -> None:
        pool = await self._pool_get()
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id TEXT PRIMARY KEY,
                    playbook_slug TEXT NOT NULL,
                    section TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({self.dim}) NOT NULL
                );
                """
            )
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self._table}_embedding_idx "
                f"ON {self._table} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
            )

    async def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        pool = await self._pool_get()
        async with pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {self._table} (id, playbook_slug, section, content, metadata, embedding)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (id) DO UPDATE SET
                    playbook_slug = EXCLUDED.playbook_slug,
                    section = EXCLUDED.section,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding;
                """,
                [
                    (
                        c.id,
                        c.playbook_slug,
                        c.section,
                        c.content,
                        _json_dumps(c.metadata),
                        np.asarray(e, dtype=np.float32),
                    )
                    for c, e in zip(chunks, embeddings)
                ],
            )

    async def search(self, query_embedding: list[float], k: int = 3) -> list[SearchResult]:
        pool = await self._pool_get()
        q = np.asarray(query_embedding, dtype=np.float32)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, playbook_slug, section, content, metadata,
                       1 - (embedding <=> $1) AS score
                FROM {self._table}
                ORDER BY embedding <=> $1
                LIMIT $2;
                """,
                q,
                k,
            )
        out: list[SearchResult] = []
        for row in rows:
            meta = dict(row["metadata"]) if row["metadata"] else {}
            out.append(
                SearchResult(
                    chunk=Chunk(
                        id=row["id"],
                        playbook_slug=row["playbook_slug"],
                        section=row["section"],
                        content=row["content"],
                        metadata=meta,
                    ),
                    score=float(row["score"]),
                )
            )
        return out

    async def count(self) -> int:
        pool = await self._pool_get()
        async with pool.acquire() as conn:
            return int(await conn.fetchval(f"SELECT count(*) FROM {self._table}"))

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, default=str)
