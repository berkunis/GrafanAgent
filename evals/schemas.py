"""Schemas the LLM judge emits and the runner aggregates."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agents.router.schemas import RoutingDecision


class JudgeVerdict(BaseModel):
    """One LLM-judge decision per golden case. Emitted via forced tool-use."""

    skill_correct: bool = Field(
        ..., description="True iff the actual skill exactly matches the expected skill."
    )
    confidence_calibration: int = Field(
        ...,
        ge=0,
        le=5,
        description=(
            "0 — wildly miscalibrated (high confidence on a wrong answer or vice versa). "
            "3 — roughly right. 5 — well-calibrated."
        ),
    )
    rationale_quality: int = Field(
        ...,
        ge=0,
        le=5,
        description=(
            "0 — missing, generic, or contradicts the payload. "
            "3 — accurate but bland. 5 — one specific sentence that names the decisive feature."
        ),
    )
    overall_score: int = Field(
        ..., ge=0, le=5, description="Holistic score. Weight skill correctness heavily."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable problems — each ≤ 100 chars. Empty when clean.",
    )


class EvalCaseResult(BaseModel):
    """Row-level result combining the router's response and the judge's verdict."""

    case_id: str
    signal_type: str
    expected_skill: str
    actual_skill: str | None
    actual_decision: dict[str, Any] | None = None
    judge: JudgeVerdict | None = None
    passed: bool                     # skill_correct AND overall_score >= pass_threshold
    error: str | None = None         # populated when router or judge raised

    @property
    def overall_score(self) -> int:
        return self.judge.overall_score if self.judge else 0


class EvalRunSummary(BaseModel):
    """Per-run aggregate. What the metrics exporter and the CLI print."""

    total: int
    passed: int
    pass_rate: float
    mean_overall_score: float
    mean_confidence_calibration: float
    mean_rationale_quality: float
    by_skill: dict[str, dict[str, float]] = Field(default_factory=dict)


def make_case_result(
    case_id: str,
    signal_type: str,
    expected_skill: str,
    decision: RoutingDecision | None,
    judge: JudgeVerdict | None,
    pass_threshold: int,
    error: str | None = None,
) -> EvalCaseResult:
    actual = decision.skill if decision else None
    actual_dump = decision.model_dump() if decision else None
    passed = bool(
        judge
        and judge.skill_correct
        and judge.overall_score >= pass_threshold
    )
    return EvalCaseResult(
        case_id=case_id,
        signal_type=signal_type,
        expected_skill=expected_skill,
        actual_skill=actual,
        actual_decision=actual_dump,
        judge=judge,
        passed=passed,
        error=error,
    )
