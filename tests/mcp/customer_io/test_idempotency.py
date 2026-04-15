from mcp_servers.customer_io.idempotency import IdempotencyCache, derive_key


def test_put_and_get_roundtrip():
    ic = IdempotencyCache(ttl_seconds=60)
    ic.put("k", {"status": "ok"})
    assert ic.get("k") == {"status": "ok"}


def test_miss_returns_none():
    assert IdempotencyCache().get("never") is None


def test_derive_key_is_stable_and_unique_per_op():
    assert derive_key("sig-1", "broadcast:x") == derive_key("sig-1", "broadcast:x")
    assert derive_key("sig-1", "broadcast:x") != derive_key("sig-1", "segment:99")
    assert derive_key("sig-1", "x") != derive_key("sig-2", "x")
