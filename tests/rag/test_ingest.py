from pathlib import Path

import pytest

from rag.embeddings import HashEmbedder
from rag.ingest import ingest, load_corpus
from rag.store import InMemoryVectorStore

CORPUS = Path(__file__).resolve().parent.parent.parent / "rag" / "corpus"


def test_load_corpus_finds_playbooks():
    chunks = load_corpus(CORPUS)
    assert len(chunks) > 0
    slugs = {c.playbook_slug for c in chunks}
    assert "aha-moment-free-user" in slugs
    # Every chunk has its source playbook slug + a non-empty section + content.
    for c in chunks:
        assert c.playbook_slug
        assert c.section
        assert c.content


def test_chunks_carry_signal_type_metadata():
    chunks = load_corpus(CORPUS)
    aha = [c for c in chunks if c.playbook_slug == "aha-moment-free-user"]
    assert aha
    assert "aha_moment_threshold" in aha[0].metadata["signal_types"]


@pytest.mark.asyncio
async def test_ingest_populates_store():
    e = HashEmbedder()
    store = InMemoryVectorStore(dim=e.dim)
    n = await ingest(embedder=e, store=store, corpus_dir=CORPUS)
    assert n > 0
    assert await store.count() == n
