"""Tiny in-process idempotency cache.

Every Customer.io write carries a key derived from `signal_id`; if we've seen
the key before within the TTL we return the cached result instead of issuing
the call again. For a real multi-replica deployment swap this for Firestore
or Redis; the interface is narrow enough to keep either impl drop-in.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    result: Any
    expires_at: float


class IdempotencyCache:
    def __init__(self, *, ttl_seconds: float = 3600.0):
        self._store: dict[str, _Entry] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.result

    def put(self, key: str, result: Any) -> None:
        self._store[key] = _Entry(result=result, expires_at=time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()


def derive_key(signal_id: str, op: str) -> str:
    """Canonical idempotency key. Keep the format stable; replaying a signal
    must produce the exact same key across processes."""
    return f"cio:{op}:{signal_id}"
