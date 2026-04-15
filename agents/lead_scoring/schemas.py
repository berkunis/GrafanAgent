"""Schemas flowing through the lead-scoring agent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agents.router.schemas import RoutingDecision, Signal

Priority = Literal["high", "medium", "low"]


class LeadScoringTask(BaseModel):
    signal: Signal
    decision: RoutingDecision


class LeadContext(BaseModel):
    """Slim BQ enrichment the synthesis prompt consumes."""

    lead_id: str
    email_domain: str | None = None
    company: str | None = None
    title: str | None = None
    seniority: str | None = None
    plan: str | None = None
    lifecycle_stage: str | None = None
    recent_event_types: list[str] = Field(default_factory=list)
    crm_stage: str | None = None
    do_not_contact: bool = False
    intent_score: float | None = None
    raw_rows: list[dict[str, Any]] = Field(default_factory=list)


class PlaybookHit(BaseModel):
    playbook_slug: str
    section: str
    content: str
    score: float


class Enrichment(BaseModel):
    lead_context: LeadContext | None = None
    playbooks: list[PlaybookHit] = Field(default_factory=list)
    partial: bool = False
    errors: dict[str, str] = Field(default_factory=dict)


class LeadScore(BaseModel):
    """The Sonnet-synthesized score. Emitted via forced tool-use."""

    fit_score: int = Field(..., ge=0, le=100)
    priority: Priority
    top_drivers: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Top 3–5 specific drivers in plain English; each ≤ 100 chars.",
    )
    recommended_action: str = Field(
        ...,
        max_length=300,
        description="One-sentence next action mapped to priority (SDR handoff, tier-2 sequence, nurture).",
    )
    rationale: str = Field(..., max_length=400)
    playbook_slug: str | None = Field(None, description="RAG playbook that shaped the scoring.")


class LeadScoringOutput(BaseModel):
    signal_id: str
    enrichment: Enrichment
    score: dict[str, Any]
    latency_ms: int
    # HITL gates the SDR Slack handoff for high-priority scores; medium/low
    # write to CRM directly without a human gate.
    hitl_id: str | None = None
    hitl_state: str | None = None
    hitl_decided_by: str | None = None
    hitl_decided_at: str | None = None
    executed: bool = False
    execution_detail: dict[str, Any] | None = None
