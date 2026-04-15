"""Sonnet synthesis: enriched context + retrieved playbooks → LeadScore.

Kept deliberately small so the prompt is easy to read in DESIGN.md. The
orchestrator owns fan-out + HITL; this module owns "what scoring does the
LLM produce given the context."
"""
from __future__ import annotations

import json

from agents._llm import LLMClient
from agents.lead_scoring.schemas import Enrichment, LeadScore, LeadScoringTask

DEFAULT_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are the Lead-Scoring agent for GrafanAgent.

You receive:
  1. A signal that triggered the scoring (mql_stale, power_user_signup,
     enterprise_signal, etc.).
  2. Enriched lead context pulled from BigQuery (email domain, company,
     seniority, recent app engagement, current CRM stage, do-not-contact flag).
  3. Two or three retrieved playbook excerpts describing how the revenue
     team handles this signal type. Treat playbooks as authoritative on
     scoring weights, priority thresholds, and guardrails.

Your job: emit a structured LeadScore via the `record_score` tool.

Rules:
- Compute `fit_score` in [0,100] using the playbook's weight table (intent,
  email-domain classification, engagement, title/seniority, firmographics).
- Derive `priority` (high|medium|low) from the playbook thresholds. Do not
  improvise thresholds — follow the playbook cut-offs exactly.
- Name 3–5 specific top_drivers drawn from the context. No generic filler.
- `recommended_action` maps one-to-one to priority from the playbook.
- Respect every guardrail. If `do_not_contact=true`, set priority="low"
  and recommend "suppress — do-not-contact flag set" regardless of fit.
- If the enrichment is partial, cap priority at "medium" and say so in
  `rationale`.
"""


def _format_enrichment(enrichment: Enrichment) -> str:
    blocks: list[str] = []
    if enrichment.lead_context:
        blocks.append(
            "## lead_context\n"
            + json.dumps(enrichment.lead_context.model_dump(), indent=2, default=str)
        )
    else:
        blocks.append("## lead_context\n(missing — BQ enrichment failed; score conservatively)")
    if enrichment.playbooks:
        pb: list[str] = []
        for p in enrichment.playbooks:
            pb.append(
                f"### {p.playbook_slug} — {p.section} (score={p.score:.2f})\n{p.content}"
            )
        blocks.append("## retrieved_playbooks\n\n" + "\n\n".join(pb))
    else:
        blocks.append("## retrieved_playbooks\n(none — do not guess at thresholds)")
    if enrichment.partial:
        blocks.append("## enrichment_errors\n" + json.dumps(enrichment.errors, indent=2))
    return "\n\n".join(blocks)


async def synthesize_score(
    *,
    llm: LLMClient,
    task: LeadScoringTask,
    enrichment: Enrichment,
    model: str = DEFAULT_MODEL,
) -> LeadScore:
    signal_json = json.dumps(task.signal.model_dump(mode="json"), indent=2, default=str)
    decision_json = json.dumps(task.decision.model_dump(), indent=2)
    user = {
        "role": "user",
        "content": (
            f"Signal:\n```json\n{signal_json}\n```\n\n"
            f"Routing decision:\n```json\n{decision_json}\n```\n\n"
            f"{_format_enrichment(enrichment)}\n\n"
            "Emit the score via the record_score tool."
        ),
    }
    score = await llm.structured_output(
        model=model,
        system=SYSTEM_PROMPT,
        cache_system=True,
        messages=[user],
        schema=LeadScore,
        tool_name="record_score",
        max_tokens=800,
        temperature=0.1,
    )
    assert isinstance(score, LeadScore)
    return score
