"""Token → USD cost conversion for Anthropic models.

Prices in USD per 1M tokens, kept here as a single source of truth. Supports
cache-read (10% of input), cache-write (125% of input), and regular input/
output so the dashboard can break down cost by bucket and quantify the
savings from prompt caching.

Source: Anthropic public pricing page. Bump the table when new models ship
or prices change; every consumer (span attrs, Mimir counter, CLI cost
estimate) reads from `PRICES` so there is no drift.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    # Multipliers relative to input_per_mtok. Matches Anthropic's contract:
    # cache-writes cost 1.25x input, cache-reads cost 0.10x input.
    cache_write_multiplier: float = 1.25
    cache_read_multiplier: float = 0.10


@dataclass(frozen=True)
class CostBreakdown:
    """Per-call cost attribution. `total` is the sum; the individual fields
    feed the stacked Grafana cost panel."""

    input_usd: float
    output_usd: float
    cache_write_usd: float
    cache_read_usd: float

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.output_usd + self.cache_write_usd + self.cache_read_usd


PRICES: dict[str, ModelPrice] = {
    # Claude 4.5 / 4.6 family (Apr 2026)
    "claude-haiku-4-5":          ModelPrice(input_per_mtok=1.00,  output_per_mtok=5.00),
    "claude-sonnet-4-5":         ModelPrice(input_per_mtok=3.00,  output_per_mtok=15.00),
    "claude-opus-4-6":           ModelPrice(input_per_mtok=15.00, output_per_mtok=75.00),
    # 3.x snapshots kept for VCR back-compat.
    "claude-3-5-haiku-latest":   ModelPrice(input_per_mtok=0.80,  output_per_mtok=4.00),
    "claude-3-5-sonnet-latest":  ModelPrice(input_per_mtok=3.00,  output_per_mtok=15.00),
}


def cost_breakdown(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> CostBreakdown:
    """Per-call cost attribution. Unknown models return zeros rather than
    raising — telemetry must never break a request."""
    price = PRICES.get(model)
    if price is None:
        return CostBreakdown(0.0, 0.0, 0.0, 0.0)
    per_mtok = 1_000_000
    return CostBreakdown(
        input_usd=input_tokens * price.input_per_mtok / per_mtok,
        output_usd=output_tokens * price.output_per_mtok / per_mtok,
        cache_write_usd=cache_creation_tokens
        * price.input_per_mtok
        * price.cache_write_multiplier
        / per_mtok,
        cache_read_usd=cache_read_tokens
        * price.input_per_mtok
        * price.cache_read_multiplier
        / per_mtok,
    )


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Thin shim over cost_breakdown for call-sites that only need the total."""
    return cost_breakdown(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
    ).total_usd
