"""Pydantic models that flow through the router.

`Signal` is the input — a marketing-ops event from BQ, Pub/Sub, a webhook, or
the CLI. `RoutingDecision` is the structured output the LLM (or the fallback
chain) emits. `RouterResponse` is what the HTTP handler returns to the caller.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Skill(str, Enum):
    LIFECYCLE = "lifecycle"
    LEAD_SCORING = "lead_scoring"
    ATTRIBUTION = "attribution"
    HITL = "hitl"  # escape hatch — no skill agent claims this signal


SkillLiteral = Literal["lifecycle", "lead_scoring", "attribution", "hitl"]


class Signal(BaseModel):
    """A single marketing-ops event the router classifies."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Stable signal identifier; used as the idempotency key downstream.")
    type: str = Field(..., description="Signal type, e.g. 'aha_moment_threshold', 'mql_stale'.")
    source: str = Field(..., description="Where it came from: 'bigquery', 'pubsub', 'webhook', 'cli'.")
    user_id: str | None = Field(None, description="Internal user/account identifier, if known.")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict, description="Signal-specific data.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Routing hints, traceparent, etc.")


class RoutingDecision(BaseModel):
    """The router's per-signal decision. Emitted by the LLM via tool-forced JSON."""

    skill: SkillLiteral = Field(
        ..., description="Which skill agent should handle this signal (or 'hitl')."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Self-reported classifier confidence in [0, 1]."
    )
    rationale: str = Field(
        ..., max_length=400, description="One-sentence human-readable reason for the choice."
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured payload the skill agent will need (e.g. extracted user_id).",
    )


class FallbackRung(str, Enum):
    """Which step of the fallback ladder produced the final decision."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    RULE = "rule"
    HITL = "hitl"


class RouterResponse(BaseModel):
    """Full response returned by POST /signal — useful for the CLI and tests."""

    signal_id: str
    decision: RoutingDecision
    rung_used: FallbackRung
    models_consulted: list[str]
    latency_ms: int
