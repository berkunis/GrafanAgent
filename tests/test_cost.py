"""Cost model — verifies per-bucket pricing + cache multipliers."""
from __future__ import annotations

import math

from observability.cost import PRICES, cost_breakdown, cost_usd


def _close(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=tol)


def test_known_model_prices_exist():
    for model in ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-6"):
        assert model in PRICES
        p = PRICES[model]
        assert p.input_per_mtok > 0
        assert p.output_per_mtok > p.input_per_mtok  # output is always pricier
        assert p.cache_read_multiplier < 1.0
        assert p.cache_write_multiplier > 1.0


def test_cost_breakdown_without_cache():
    b = cost_breakdown(
        "claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    assert _close(b.input_usd, 3.0)
    assert _close(b.output_usd, 7.5)
    assert b.cache_read_usd == 0.0
    assert b.cache_write_usd == 0.0
    assert _close(b.total_usd, 10.5)


def test_cost_breakdown_with_cache_read_is_cheaper():
    """Same total input tokens — half served from cache read should be cheaper."""
    no_cache = cost_breakdown("claude-sonnet-4-5", input_tokens=1_000_000)
    with_cache = cost_breakdown(
        "claude-sonnet-4-5",
        input_tokens=500_000,
        cache_read_tokens=500_000,
    )
    assert with_cache.total_usd < no_cache.total_usd
    # Cache read should be 10% of input price.
    assert _close(with_cache.cache_read_usd, no_cache.input_usd * 0.5 * 0.10)


def test_cost_breakdown_cache_write_is_premium():
    """Cache-write is priced at 125% of input."""
    plain = cost_breakdown("claude-haiku-4-5", input_tokens=1_000_000)
    with_write = cost_breakdown("claude-haiku-4-5", cache_creation_tokens=1_000_000)
    assert with_write.cache_write_usd > plain.input_usd
    assert _close(with_write.cache_write_usd, plain.input_usd * 1.25)


def test_unknown_model_returns_zero():
    assert cost_usd("nonexistent-model", 100, 100) == 0.0
    b = cost_breakdown("nonexistent-model", input_tokens=9999, output_tokens=9999)
    assert b.total_usd == 0.0


def test_cost_usd_matches_breakdown_total():
    args = dict(input_tokens=1000, output_tokens=400, cache_read_tokens=2000, cache_creation_tokens=500)
    total = cost_usd("claude-sonnet-4-5", args["input_tokens"], args["output_tokens"],
                     cache_read_tokens=args["cache_read_tokens"],
                     cache_creation_tokens=args["cache_creation_tokens"])
    b = cost_breakdown("claude-sonnet-4-5", **args)
    assert _close(total, b.total_usd)
