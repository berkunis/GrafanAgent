"""Deterministic rule table — the third rung of the fallback chain.

Hand-curated mapping from known signal types to the right skill agent. The
LLM is wrong on these rarely, but if both Haiku and Sonnet wobble we want a
non-LLM safety net so we don't page a human for an unambiguous case.

Edit this table when you add a new signal type with an obvious owner. If a
signal type belongs in the table, add a golden case for it in
`evals/golden_set.jsonl` so the LLM gets evaluated on it too.
"""
from __future__ import annotations

from agents.router.schemas import RoutingDecision, SkillLiteral

# Signal type → skill. Keep in sync with evals/golden_set.jsonl.
RULE_TABLE: dict[str, SkillLiteral] = {
    "aha_moment_threshold":  "lifecycle",
    "trial_expiring":        "lifecycle",
    "usage_drop":            "lifecycle",
    "feature_unlock":        "lifecycle",
    "mql_stale":             "lead_scoring",
    "power_user_signup":     "lead_scoring",
    "enterprise_signal":     "lead_scoring",
    "conversion_milestone":  "attribution",
    "campaign_completed":    "attribution",
    "channel_attribution_q": "attribution",
}


def rule_lookup(signal_type: str) -> RoutingDecision | None:
    """Return a rule-based decision, or None if no rule matches."""
    skill = RULE_TABLE.get(signal_type)
    if skill is None:
        return None
    return RoutingDecision(
        skill=skill,
        confidence=1.0,
        rationale=f"Deterministic rule: signal type '{signal_type}' is owned by {skill}.",
        payload={},
    )
