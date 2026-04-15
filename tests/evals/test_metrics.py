"""Metric-emission smoke test — exercises every code path without asserting
on stdout. Ensures no exceptions fire when OTel isn't fully initialised."""
from __future__ import annotations

from evals.metrics import emit
from evals.schemas import EvalCaseResult, EvalRunSummary, JudgeVerdict


def _case(passed: bool, skill: str) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=f"c-{skill}",
        signal_type=f"{skill}_signal",
        expected_skill=skill,
        actual_skill=skill,
        judge=JudgeVerdict(
            skill_correct=True,
            confidence_calibration=4,
            rationale_quality=4,
            overall_score=5 if passed else 2,
        ),
        passed=passed,
    )


def test_emit_runs_without_error():
    results = [_case(True, "lifecycle"), _case(False, "attribution")]
    summary = EvalRunSummary(
        total=2,
        passed=1,
        pass_rate=0.5,
        mean_overall_score=3.5,
        mean_confidence_calibration=4.0,
        mean_rationale_quality=4.0,
        by_skill={
            "lifecycle": {"total": 1, "passed": 1, "pass_rate": 1.0, "mean_overall_score": 5.0},
            "attribution": {"total": 1, "passed": 0, "pass_rate": 0.0, "mean_overall_score": 2.0},
        },
    )
    # Must not raise regardless of OTel configuration state.
    emit(results=results, summary=summary, set_name="golden_set", mode="llm")
