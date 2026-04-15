"""Runner tests — mock router + FakeAnthropic-backed judge."""
from __future__ import annotations

from pathlib import Path

import pytest

from agents._llm import LLMClient
from agents.router.schemas import RoutingDecision, Signal
from evals.golden import load_cases
from evals.runner import RunConfig, run_case, run_suite, summarize
from evals.schemas import make_case_result
from tests.conftest import FakeAnthropic, tool_use_response

GOLDEN = Path(__file__).resolve().parent.parent.parent / "evals" / "golden_set.jsonl"


def _judge_response(*, skill_correct: bool = True, overall: int = 5):
    return tool_use_response(
        tool_name="record_verdict",
        tool_input={
            "skill_correct": skill_correct,
            "confidence_calibration": 4,
            "rationale_quality": 4,
            "overall_score": overall,
            "issues": [] if skill_correct else ["mismatch"],
        },
        model="claude-sonnet-4-5",
    )


@pytest.mark.asyncio
async def test_run_case_full_path():
    async def router(signal: Signal) -> RoutingDecision:
        return RoutingDecision(
            skill="lifecycle",
            confidence=0.92,
            rationale="aha-moment",
            payload={},
        )

    llm = LLMClient(client=FakeAnthropic([_judge_response(overall=5)]), agent="judge")  # type: ignore[arg-type]
    cases = load_cases(GOLDEN)
    result = await run_case(cases[0], router=router, judge_llm=llm, cfg=RunConfig())
    assert result.passed is True
    assert result.actual_skill == "lifecycle"
    assert result.judge and result.judge.overall_score == 5
    assert result.error is None


@pytest.mark.asyncio
async def test_run_case_fails_below_threshold():
    async def router(signal: Signal) -> RoutingDecision:
        return RoutingDecision(skill="lifecycle", confidence=0.3, rationale="weak", payload={})

    llm = LLMClient(
        client=FakeAnthropic([_judge_response(skill_correct=True, overall=2)]), agent="judge"
    )  # type: ignore[arg-type]
    cases = load_cases(GOLDEN)
    result = await run_case(cases[0], router=router, judge_llm=llm, cfg=RunConfig(pass_threshold=4))
    assert result.passed is False  # overall=2 < threshold=4


@pytest.mark.asyncio
async def test_run_case_records_router_error():
    async def bad_router(signal: Signal) -> RoutingDecision:
        raise RuntimeError("anthropic outage")

    llm = LLMClient(client=FakeAnthropic([]), agent="judge")  # type: ignore[arg-type]
    cases = load_cases(GOLDEN)
    result = await run_case(cases[0], router=bad_router, judge_llm=llm, cfg=RunConfig())
    assert result.passed is False
    assert result.error and "router" in result.error
    assert result.judge is None


@pytest.mark.asyncio
async def test_run_suite_summary_aggregates():
    async def router(signal: Signal) -> RoutingDecision:
        # Always returns the expected skill so summary logic runs the pass path.
        return RoutingDecision(
            skill=signal.metadata.get("expected_skill", "lifecycle") or "lifecycle",
            confidence=0.9,
            rationale="ok",
            payload={},
        )

    # Build a tiny in-memory suite so we control the scale.
    cases = load_cases(GOLDEN)[:3]
    # Inject expected_skill into signal.metadata for the toy router above.
    for c in cases:
        c.signal["metadata"] = {"expected_skill": c.expected_skill}

    responses = [_judge_response(overall=5) for _ in cases]
    llm = LLMClient(client=FakeAnthropic(responses), agent="judge")  # type: ignore[arg-type]

    # Override the router to actually pick the expected skill this time.
    async def r(signal: Signal) -> RoutingDecision:
        return RoutingDecision(
            skill=signal.metadata["expected_skill"],
            confidence=0.9,
            rationale="ok",
            payload={},
        )

    results, summary = await run_suite(router=r, judge_llm=llm, cases=cases, cfg=RunConfig())
    assert summary.total == len(cases)
    assert summary.passed == len(cases)
    assert summary.pass_rate == 1.0
    assert summary.mean_overall_score == 5.0
    assert set(summary.by_skill.keys()) == {c.expected_skill for c in cases}


def test_summarize_handles_empty():
    s = summarize([])
    assert s.total == 0
    assert s.pass_rate == 0.0
    assert s.mean_overall_score == 0.0


def test_make_case_result_requires_both_skill_and_score():
    from evals.schemas import JudgeVerdict

    r = make_case_result(
        case_id="c",
        signal_type="t",
        expected_skill="lifecycle",
        decision=RoutingDecision(skill="lifecycle", confidence=1.0, rationale="x"),
        judge=JudgeVerdict(skill_correct=True, confidence_calibration=5, rationale_quality=5, overall_score=3),
        pass_threshold=4,
    )
    assert r.passed is False  # overall=3 < threshold=4 even though skill correct
