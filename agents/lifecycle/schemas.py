"""Schemas that flow through the lifecycle agent."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agents.router.schemas import RoutingDecision, Signal


class LifecycleTask(BaseModel):
    """What the router hands to the lifecycle agent."""

    signal: Signal
    decision: RoutingDecision


class UserContext(BaseModel):
    """Slim BigQuery user enrichment the synthesis prompt consumes."""

    user_id: str
    plan: str | None = None
    lifecycle_stage: str | None = None
    company: str | None = None
    country: str | None = None
    signed_up_at: str | None = None
    recent_event_types: list[str] = Field(default_factory=list)
    raw_rows: list[dict[str, Any]] = Field(default_factory=list)


class PlaybookHit(BaseModel):
    playbook_slug: str
    section: str
    content: str
    score: float


class Enrichment(BaseModel):
    user_context: UserContext | None = None
    playbooks: list[PlaybookHit] = Field(default_factory=list)
    current_campaigns: list[str] = Field(default_factory=list)
    partial: bool = Field(
        default=False,
        description="True when one or more fan-out legs failed; the draft proceeds on partial context.",
    )
    errors: dict[str, str] = Field(default_factory=dict)


class DraftSpec(BaseModel):
    """Exactly what the LLM synthesises. Converted into a CampaignDraft by the orchestrator."""

    audience_segment: str = Field(..., description="Short segment name, e.g. 'free_activated_today'.")
    channel: str = Field(..., description="email, in_product, slack_alert, or email+in_product.")
    subject: str = Field(..., description="Subject line (email) or heading (in-product).")
    body_markdown: str = Field(..., description="Message body in markdown, 60–180 words.")
    call_to_action: str = Field(..., description="Single primary CTA the message drives toward.")
    rationale: str = Field(..., max_length=400, description="One sentence on why this message for this user.")
    playbook_slug: str | None = Field(None, description="Which retrieved playbook shaped the draft.")


class LifecycleOutput(BaseModel):
    """What the lifecycle agent returns to its caller."""

    signal_id: str
    enrichment: Enrichment
    draft: dict[str, Any]
    latency_ms: int
