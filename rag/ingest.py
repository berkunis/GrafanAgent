"""Corpus ingestion: markdown → chunks → embeddings → store.

Each markdown file in `rag/corpus/` is one playbook. Frontmatter carries
metadata (slug, signal_types the playbook is relevant to). The body is split
by H2 headings (`## `) into sections; each section becomes a `Chunk`. For
playbooks without H2 headings, the whole body is one chunk labeled `body`.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Iterable

import frontmatter

from rag.embeddings import Embedder
from rag.schemas import Chunk
from rag.store import VectorStore

CORPUS_DIR = Path(__file__).parent / "corpus"


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        post = frontmatter.load(path)
        slug = post.metadata.get("slug") or path.stem
        meta_base: dict = {
            "signal_types": list(post.metadata.get("signal_types", [])),
            "audience": post.metadata.get("audience"),
            "channel": post.metadata.get("channel"),
            "source_file": path.name,
        }
        for section, body in _split_sections(post.content):
            if not body.strip():
                continue
            chunks.append(
                Chunk(
                    id=f"{slug}::{_slugify(section)}",
                    playbook_slug=slug,
                    section=section,
                    content=body.strip(),
                    metadata=meta_base,
                )
            )
    return chunks


def _split_sections(markdown_body: str) -> Iterable[tuple[str, str]]:
    """Split by H2. If no H2 present, yield the full body as 'body'."""
    parts = re.split(r"^##\s+(.+)$", markdown_body, flags=re.MULTILINE)
    # parts[0] = preamble before first H2; then alternating (heading, body).
    preamble = parts[0].strip()
    if not parts[1:]:
        yield "body", preamble
        return
    if preamble:
        yield "intro", preamble
    it = iter(parts[1:])
    for heading in it:
        body = next(it, "")
        yield heading.strip(), body


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


async def ingest(
    *,
    embedder: Embedder,
    store: VectorStore,
    corpus_dir: Path = CORPUS_DIR,
    batch_size: int = 16,
) -> int:
    chunks = load_corpus(corpus_dir)
    if not chunks:
        return 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        vectors = await embedder.embed([c.content for c in batch])
        await store.upsert(batch, vectors)
    return len(chunks)


# ---- CLI entrypoint ----


async def _main() -> None:
    import os

    from rag.embeddings import HashEmbedder, VertexEmbedder
    from rag.store import InMemoryVectorStore, PgVectorStore

    backend = os.getenv("RAG_BACKEND", "memory")
    embedder: Embedder
    store: VectorStore

    if os.getenv("RAG_EMBEDDER", "hash") == "vertex":
        embedder = VertexEmbedder()
    else:
        embedder = HashEmbedder()

    if backend == "pgvector":
        store = PgVectorStore(dim=embedder.dim)
        await store.init_schema()
    else:
        store = InMemoryVectorStore(dim=embedder.dim)

    count = await ingest(embedder=embedder, store=store)
    print(f"ingested {count} chunks into {backend}")

    if hasattr(store, "close"):
        await store.close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    asyncio.run(_main())
