"""Schemas flowing through the attribution agent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agents.router.schemas import RoutingDecision, Signal

Confidence = Literal["high", "medium", "low"]


class AttributionTask(BaseModel):
    signal: Signal
    decision: RoutingDecision


class TouchpointRow(BaseModel):
    campaign_id: str
    channel: str
    touch_at: str
    utm_source: str | None = None


class ConversionContext(BaseModel):
    user_id: str | None = None
    plan_transition: str | None = None
    cohort_size: int | None = None
    touches: list[TouchpointRow] = Field(default_factory=list)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)


class PlaybookHit(BaseModel):
    playbook_slug: str
    section: str
    content: str
    score: float


class Enrichment(BaseModel):
    conversion_context: ConversionContext | None = None
    playbooks: list[PlaybookHit] = Field(default_factory=list)
    partial: bool = False
    errors: dict[str, str] = Field(default_factory=dict)


class MultiTouchEntry(BaseModel):
    campaign_id: str = Field(..., description="Campaign id or 'unattributed'.")
    channel: str
    weight: float = Field(..., ge=0.0, le=1.0)


class AttributionReport(BaseModel):
    """The Sonnet-synthesized analysis. Emitted via forced tool-use."""

    first_touch: str = Field(..., description="First-touch campaign_id or 'unattributed'.")
    last_touch: str = Field(..., description="Last-touch campaign_id or 'unattributed'.")
    multi_touch: list[MultiTouchEntry] = Field(
        ...,
        description="Weighted multi-touch list. Weights must sum to 1.0 (± 0.01 rounding).",
    )
    top_driver_rationale: str = Field(
        ...,
        max_length=400,
        description="One sentence naming the single strongest driver + evidence.",
    )
    three_line_verdict: str = Field(
        ...,
        max_length=500,
        description="What worked / what didn't / what to change — three lines.",
    )
    confidence: Confidence
    recommend_rerun: bool = Field(..., description="For campaign debriefs only; ignored for conversion reports.")
    playbook_slug: str | None = None

    @field_validator("multi_touch")
    @classmethod
    def _weights_sum(cls, v: list[MultiTouchEntry]) -> list[MultiTouchEntry]:
        if not v:
            return v
        total = sum(entry.weight for entry in v)
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"multi_touch weights must sum to 1.0 (±0.01); got {total:.3f}")
        return v


class AttributionOutput(BaseModel):
    signal_id: str
    enrichment: Enrichment
    report: dict[str, Any]
    latency_ms: int
    posted_to_channel: str | None = None
    posted_message_detail: dict[str, Any] | None = None
