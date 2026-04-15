"""Synthesis step: take enriched context + retrieved playbooks, emit a DraftSpec.

Kept in its own module so the prompt and structured-output call are easy to
read, evaluate, and iterate on. The orchestrator owns the fan-out; this module
owns the "what do we want the LLM to write" question.
"""
from __future__ import annotations

import json
from typing import Any

from agents._llm import LLMClient
from agents.lifecycle.schemas import DraftSpec, Enrichment, LifecycleTask

DEFAULT_SYNTHESIS_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are the Lifecycle Personalization agent for GrafanAgent.

You receive:
  1. A signal that triggered lifecycle work (aha-moment crossed, trial expiring, etc.)
  2. Enriched user context pulled from BigQuery (plan, recent behavior).
  3. Current Customer.io campaign memberships for the user (so we don't double-enrol).
  4. Two or three retrieved playbook excerpts describing how the marketing team has
     handled this signal type in the past. Treat playbooks as authoritative guidance —
     not verbatim copy, but the source of truth on audience, channel, message angle,
     and guardrails.

Your job: produce a single campaign draft that the HITL Slack reviewer will approve,
reject, or edit. Use the `record_draft` tool.

Rules:
- Ground the draft in the retrieved playbooks. If the playbooks disagree, pick the
  one that matches the user's plan + behavior and name it in `playbook_slug`.
- Respect every guardrail from the playbook — no urgency panic copy, no competitor
  refs, no PII, no naming specific customer data values.
- Keep bodies 60–180 words, first person plural, warm and specific.
- One primary CTA. No secondary CTAs in this phase.
- If the user is already enrolled in a campaign that would overlap, explain that in
  `rationale` and propose a non-overlapping angle anyway.
- If the enrichment is partial (errors present), acknowledge in `rationale` and keep
  the draft safer/more generic.
"""


def _format_enrichment(enrichment: Enrichment) -> str:
    blocks: list[str] = []
    if enrichment.user_context:
        blocks.append("## user_context\n" + json.dumps(enrichment.user_context.model_dump(), indent=2, default=str))
    if enrichment.current_campaigns:
        blocks.append("## current_campaigns\n" + ", ".join(enrichment.current_campaigns))
    else:
        blocks.append("## current_campaigns\n(none — user is not currently in any campaigns)")
    if enrichment.playbooks:
        pb_chunks: list[str] = []
        for pb in enrichment.playbooks:
            pb_chunks.append(
                f"### {pb.playbook_slug} — {pb.section} (score={pb.score:.2f})\n{pb.content}"
            )
        blocks.append("## retrieved_playbooks\n\n" + "\n\n".join(pb_chunks))
    else:
        blocks.append("## retrieved_playbooks\n(none returned — proceed with extra caution)")
    if enrichment.partial:
        blocks.append("## enrichment_errors\n" + json.dumps(enrichment.errors, indent=2))
    return "\n\n".join(blocks)


async def synthesize_draft(
    *,
    llm: LLMClient,
    task: LifecycleTask,
    enrichment: Enrichment,
    model: str = DEFAULT_SYNTHESIS_MODEL,
) -> DraftSpec:
    signal_json = json.dumps(task.signal.model_dump(mode="json"), indent=2, default=str)
    decision_json = json.dumps(task.decision.model_dump(), indent=2)
    user_message: dict[str, Any] = {
        "role": "user",
        "content": (
            f"Signal:\n```json\n{signal_json}\n```\n\n"
            f"Routing decision:\n```json\n{decision_json}\n```\n\n"
            f"{_format_enrichment(enrichment)}\n\n"
            "Emit the draft via the record_draft tool now."
        ),
    }
    draft = await llm.structured_output(
        model=model,
        system=SYSTEM_PROMPT,
        cache_system=True,
        messages=[user_message],
        schema=DraftSpec,
        tool_name="record_draft",
        max_tokens=900,
        temperature=0.2,
    )
    assert isinstance(draft, DraftSpec)
    return draft
