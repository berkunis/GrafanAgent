"""Sonnet-based LLM judge.

Scores one router decision against the expected skill + case notes via
forced tool-use. Kept pure async so the runner can parallelise.

Every judge call goes through the shared `LLMClient` so it emits the same
OTel genai-semconv spans as production agent calls — you can see judge cost
alongside router cost on the same Grafana dashboard.
"""
from __future__ import annotations

import json

from agents._llm import LLMClient
from agents.router.schemas import RoutingDecision
from evals.schemas import JudgeVerdict

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are the quality judge for GrafanAgent's router.

You receive:
  1. A signal payload.
  2. The expected skill ("lifecycle", "lead_scoring", "attribution", or "hitl")
     and notes explaining why a human evaluator chose it.
  3. The router's actual decision (skill + confidence + rationale + payload).

Your job: emit a `record_verdict` tool call with a structured verdict.

Rubric guidelines:
- **skill_correct**: strict equality between actual and expected.
- **confidence_calibration** (0–5): high confidence on wrong skill → 0;
  low confidence on right skill also penalised; 5 = confident when right,
  uncertain when wrong.
- **rationale_quality** (0–5): 0 if missing/generic/contradictory; 5 for
  one specific sentence that names the decisive feature from the payload.
- **overall_score** (0–5): weight skill correctness heavily — a wrong skill
  can score no higher than 2 regardless of prose quality.
- **issues**: concrete, actionable (< 100 chars each). Empty when clean.

Do not repeat the inputs back. Only emit the tool call.
"""


async def judge_case(
    *,
    llm: LLMClient,
    signal: dict,
    expected_skill: str,
    notes: str,
    actual: RoutingDecision,
    model: str = DEFAULT_JUDGE_MODEL,
) -> JudgeVerdict:
    user = {
        "role": "user",
        "content": (
            "Signal:\n```json\n"
            + json.dumps(signal, indent=2, default=str)
            + "\n```\n\n"
            + f"Expected skill: **{expected_skill}**\n"
            + (f"Evaluator notes: {notes}\n\n" if notes else "\n")
            + "Router actual decision:\n```json\n"
            + json.dumps(actual.model_dump(), indent=2)
            + "\n```\n\nRecord your verdict."
        ),
    }
    verdict = await llm.structured_output(
        model=model,
        system=SYSTEM_PROMPT,
        cache_system=True,
        messages=[user],
        schema=JudgeVerdict,
        tool_name="record_verdict",
        max_tokens=500,
        temperature=0.0,
    )
    assert isinstance(verdict, JudgeVerdict)
    return verdict
