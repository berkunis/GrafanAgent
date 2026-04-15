"""Token → USD cost conversion for Anthropic models.

Prices in USD per 1M tokens, kept here as a single source of truth. Phase 6
will extend this with cache-read pricing, batch pricing, and a Grafana panel.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


# Source: Anthropic public pricing. Update as new models ship.
PRICES: dict[str, ModelPrice] = {
    # Claude 4.5 / 4.6 family
    "claude-haiku-4-5":          ModelPrice(input_per_mtok=1.00,  output_per_mtok=5.00),
    "claude-sonnet-4-5":         ModelPrice(input_per_mtok=3.00,  output_per_mtok=15.00),
    "claude-opus-4-6":           ModelPrice(input_per_mtok=15.00, output_per_mtok=75.00),
    # Older 3.x snapshots — kept for back-compat with VCR cassettes.
    "claude-3-5-haiku-latest":   ModelPrice(input_per_mtok=0.80,  output_per_mtok=4.00),
    "claude-3-5-sonnet-latest":  ModelPrice(input_per_mtok=3.00,  output_per_mtok=15.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost of a single completion. Returns 0.0 for unknown models
    rather than raising — we never want telemetry to break a request."""
    price = PRICES.get(model)
    if price is None:
        return 0.0
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
