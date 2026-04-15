"""Pydantic schemas the Customer.io MCP emits.

The draft objects are what the lifecycle agent produces; a Slack HITL card
(Phase 3) will render them. On approval we re-submit to
`trigger_broadcast` / `add_to_segment` with an idempotency key derived from
the same signal id so replays are safe.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CampaignDraft(BaseModel):
    """A proposed Customer.io campaign — not yet sent. The HITL gate will
    either approve this (→ `trigger_broadcast`) or reject it."""

    signal_id: str = Field(..., description="Source signal id; used as the idempotency key.")
    user_id: str = Field(..., description="Customer.io customer identifier.")
    audience_segment: str = Field(..., description="Segment name / id the draft targets.")
    channel: str = Field(..., description="email, in_product, slack_alert — what medium.")
    subject: str = Field(..., description="Subject line (for email) or heading.")
    body_markdown: str = Field(..., description="Body in markdown; the email builder renders it.")
    call_to_action: str = Field(..., description="One primary CTA the message drives toward.")
    playbook_slug: str | None = Field(None, description="RAG playbook that informed this draft.")
    rationale: str = Field(..., max_length=500)


class WriteResult(BaseModel):
    ok: bool
    idempotency_key: str
    already_seen: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
