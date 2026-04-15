import pytest

from rag.embeddings import HashEmbedder


@pytest.mark.asyncio
async def test_hash_embedder_is_deterministic():
    e = HashEmbedder()
    [v1] = await e.embed(["aha moment threshold crossed"])
    [v2] = await e.embed(["aha moment threshold crossed"])
    assert v1 == v2
    assert len(v1) == e.dim


@pytest.mark.asyncio
async def test_hash_embedder_similar_strings_closer_than_dissimilar():
    import math

    e = HashEmbedder()
    v_aha1 = (await e.embed(["aha moment threshold free user"]))[0]
    v_aha2 = (await e.embed(["free user aha moment"]))[0]
    v_diff = (await e.embed(["quarterly revenue attribution report"]))[0]

    def cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    assert cos(v_aha1, v_aha2) > cos(v_aha1, v_diff)


@pytest.mark.asyncio
async def test_hash_embedder_empty_list():
    assert await HashEmbedder().embed([]) == []
