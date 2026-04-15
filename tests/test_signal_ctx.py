"""Per-signal contextvars attribution — propagates through asyncio.gather."""
from __future__ import annotations

import asyncio

import pytest

from observability.signal_ctx import (
    current_attrs,
    current_signal_id,
    current_signal_type,
    signal_context,
)


def test_unset_returns_none():
    assert current_signal_id() is None
    assert current_signal_type() is None
    assert current_attrs() == {}


def test_sets_and_restores():
    with signal_context("sig-1", "aha_moment_threshold"):
        assert current_signal_id() == "sig-1"
        assert current_signal_type() == "aha_moment_threshold"
        assert current_attrs() == {
            "grafanagent.signal_id": "sig-1",
            "grafanagent.signal_type": "aha_moment_threshold",
        }
    assert current_signal_id() is None


def test_nested_contexts_stack():
    with signal_context("outer", "t1"):
        assert current_signal_id() == "outer"
        with signal_context("inner", "t2"):
            assert current_signal_id() == "inner"
            assert current_signal_type() == "t2"
        assert current_signal_id() == "outer"
        assert current_signal_type() == "t1"


@pytest.mark.asyncio
async def test_propagates_through_asyncio_gather():
    """contextvars survive asyncio task boundaries by default — this is the
    behaviour the lifecycle parallel fan-out depends on."""
    seen: list[str | None] = []

    async def leg() -> None:
        seen.append(current_signal_id())

    with signal_context("sig-parallel"):
        await asyncio.gather(leg(), leg(), leg())

    assert seen == ["sig-parallel", "sig-parallel", "sig-parallel"]
    assert current_signal_id() is None  # restored after block
