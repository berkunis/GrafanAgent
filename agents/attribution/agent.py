"""Sonnet synthesis for attribution reports."""
from __future__ import annotations

import json

from agents._llm import LLMClient
from agents.attribution.schemas import AttributionReport, AttributionTask, Enrichment

DEFAULT_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are the Attribution Analyst agent for GrafanAgent.

You receive:
  1. A signal (conversion_milestone, campaign_completed, or an ad-hoc
     channel_attribution_q).
  2. Enriched conversion context: the journey of marketing touches from BQ,
     any opportunities, cohort/plan-transition metadata.
  3. One or two retrieved playbook excerpts. The playbook is authoritative
     on methodology (first-touch / last-touch / multi-touch weighting
     rules, confidence thresholds, guardrails).

Your job: emit a structured AttributionReport via the `record_report` tool.

Rules:
- multi_touch weights MUST sum to 1.0 (± 0.01). If a touch lacks campaign
  metadata, label it `campaign_id="unattributed"` rather than dropping it.
- Name the single strongest driver in `top_driver_rationale` with a
  specific touch and evidence from the journey.
- `three_line_verdict` is literally three one-sentence lines: what worked,
  what didn't, what to change.
- Confidence: "high" when the journey is fully captured (UTMs present, all
  touches have campaigns). "medium" when gaps exist but pattern is clear.
  "low" when cohort is small (<100) or more than 30% of touches are
  unattributed — and say so in the verdict.
- `recommend_rerun` only applies to `campaign_completed` signals; set to
  `false` for conversion / ad-hoc signals.
- Never reference competitors, even if present in the raw data.
- Never expose individual user_id values in the rationale/verdict.
"""


def _format_enrichment(enrichment: Enrichment) -> str:
    blocks: list[str] = []
    if enrichment.conversion_context:
        blocks.append(
            "## conversion_context\n"
            + json.dumps(enrichment.conversion_context.model_dump(), indent=2, default=str)
        )
    if enrichment.playbooks:
        pb: list[str] = []
        for p in enrichment.playbooks:
            pb.append(f"### {p.playbook_slug} — {p.section}\n{p.content}")
        blocks.append("## retrieved_playbooks\n\n" + "\n\n".join(pb))
    else:
        blocks.append("## retrieved_playbooks\n(none — proceed cautiously, mark confidence=low)")
    if enrichment.partial:
        blocks.append("## enrichment_errors\n" + json.dumps(enrichment.errors, indent=2))
    return "\n\n".join(blocks)


async def synthesize_report(
    *,
    llm: LLMClient,
    task: AttributionTask,
    enrichment: Enrichment,
    model: str = DEFAULT_MODEL,
) -> AttributionReport:
    signal_json = json.dumps(task.signal.model_dump(mode="json"), indent=2, default=str)
    decision_json = json.dumps(task.decision.model_dump(), indent=2)
    user = {
        "role": "user",
        "content": (
            f"Signal:\n```json\n{signal_json}\n```\n\n"
            f"Routing decision:\n```json\n{decision_json}\n```\n\n"
            f"{_format_enrichment(enrichment)}\n\n"
            "Emit the report via the record_report tool."
        ),
    }
    report = await llm.structured_output(
        model=model,
        system=SYSTEM_PROMPT,
        cache_system=True,
        messages=[user],
        schema=AttributionReport,
        tool_name="record_report",
        max_tokens=1200,
        temperature=0.1,
    )
    assert isinstance(report, AttributionReport)
    return report
