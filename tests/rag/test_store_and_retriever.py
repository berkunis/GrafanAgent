import pytest

from rag.embeddings import HashEmbedder
from rag.retriever import Retriever
from rag.schemas import Chunk
from rag.store import InMemoryVectorStore


@pytest.mark.asyncio
async def test_inmemory_upsert_and_search():
    e = HashEmbedder()
    store = InMemoryVectorStore(dim=e.dim)
    chunks = [
        Chunk(id="a::trigger", playbook_slug="a", section="trigger", content="aha moment threshold free user signup"),
        Chunk(id="b::trigger", playbook_slug="b", section="trigger", content="trial expiring engaged user conversion call"),
        Chunk(id="c::trigger", playbook_slug="c", section="trigger", content="quarterly revenue attribution report"),
    ]
    vectors = await e.embed([c.content for c in chunks])
    await store.upsert(chunks, vectors)
    assert await store.count() == 3

    retriever = Retriever(e, store)
    results = await retriever.retrieve("aha moment free user signup", k=2)
    assert len(results) == 2
    assert results[0].chunk.playbook_slug == "a"
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_retriever_dim_mismatch_raises():
    e = HashEmbedder(dim=64)
    store = InMemoryVectorStore(dim=128)
    with pytest.raises(ValueError):
        Retriever(e, store)
