"""LLM classifier for the router.

Wraps a single Anthropic call that takes a `Signal` and returns a
`RoutingDecision`. The decision schema is enforced by Anthropic tool-forcing,
so we either get a valid Pydantic instance or `LLMError` — never freeform
text we have to parse.

The same `classify()` function is reused by the fallback chain for both the
Haiku and Sonnet rungs; only the model id differs.
"""
from __future__ import annotations

import json

from agents._llm import LLMClient
from agents.router.schemas import RoutingDecision, Signal

# Shared system prompt for both Haiku and Sonnet. Cached on the Anthropic side
# (`cache_system=True`) so repeat calls only pay for the unique signal text.
SYSTEM_PROMPT = """You are the routing classifier for GrafanAgent, a marketing-ops automation
platform. You receive one signal at a time and decide which skill agent should handle it.

Available skills:
- "lifecycle": personalization, lifecycle email campaigns, in-product nudges, churn prevention.
  Triggers: aha-moment thresholds, trial expirations, usage drops, feature unlocks.
- "lead_scoring": lead qualification, MQL/SQL handoff, enterprise account prioritization.
  Triggers: stale MQLs, power user signups, enterprise signals, intent data.
- "attribution": revenue attribution, campaign performance analysis, channel ROI questions.
  Triggers: conversion milestones, campaign completions, attribution questions from RevOps.
- "hitl": send to a human reviewer. Use ONLY when the signal is ambiguous, malformed, or
  obviously outside the three skills above. Prefer a confident classification when possible.

Output rules:
- Pick exactly one skill.
- Confidence is your honest self-assessment in [0, 1]. Be calibrated — confidence above 0.9
  means you would bet money on the choice.
- Rationale is one sentence, no more.
- Use the `record_decision` tool. Do not respond with prose."""


def _user_message(signal: Signal) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "Classify this signal:\n\n"
            f"```json\n{json.dumps(signal.model_dump(mode='json'), indent=2, default=str)}\n```"
        ),
    }


async def classify(
    *,
    llm: LLMClient,
    signal: Signal,
    model: str,
) -> RoutingDecision:
    """Single LLM classification pass. Caller decides which model to use."""
    decision = await llm.structured_output(
        model=model,
        system=SYSTEM_PROMPT,
        cache_system=True,
        messages=[_user_message(signal)],
        schema=RoutingDecision,
        tool_name="record_decision",
        max_tokens=400,
        temperature=0.0,
    )
    assert isinstance(decision, RoutingDecision)
    return decision
