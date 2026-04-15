"""Full LLM-mode eval runner.

Wires a golden-set loader → a router callable → the Sonnet judge → a
summary + OTel metrics emission. Parallelism is bounded (`concurrency`)
so we don't melt the Anthropic API.

The runner takes a `router` callable so tests can swap in a `FakeRouter`
that returns canned decisions without any real Anthropic traffic.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from opentelemetry import trace

from agents._llm import LLMClient
from agents.router.fallback import FallbackChain
from agents.router.schemas import RoutingDecision, Signal
from evals.golden import GOLDEN_SET_PATH, GoldenCase, load_cases
from evals.judge import judge_case
from evals.schemas import EvalCaseResult, EvalRunSummary, JudgeVerdict, make_case_result

_tracer = trace.get_tracer("evals.runner")

RouterCallable = Callable[[Signal], Awaitable[RoutingDecision]]

DEFAULT_PASS_THRESHOLD = 4       # overall_score ≥ 4 AND skill_correct → pass
DEFAULT_CONCURRENCY = 3


@dataclass(frozen=True)
class RunConfig:
    pass_threshold: int = DEFAULT_PASS_THRESHOLD
    concurrency: int = DEFAULT_CONCURRENCY
    judge_model: str = "claude-sonnet-4-5"


def fallback_chain_router(chain: FallbackChain) -> RouterCallable:
    """Adapter: use the production router as the runner's router."""

    async def _call(signal: Signal) -> RoutingDecision:
        result = await chain.decide(signal)
        return result.decision

    return _call


async def run_case(
    case: GoldenCase,
    *,
    router: RouterCallable,
    judge_llm: LLMClient,
    cfg: RunConfig,
) -> EvalCaseResult:
    with _tracer.start_as_current_span("evals.run_case") as span:
        span.set_attribute("eval.case_id", case.id)
        span.set_attribute("eval.signal_type", case.signal.get("type", ""))
        span.set_attribute("eval.expected_skill", case.expected_skill)

        try:
            signal = Signal.model_validate(case.signal)
            decision = await router(signal)
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            return make_case_result(
                case_id=case.id,
                signal_type=case.signal.get("type", ""),
                expected_skill=case.expected_skill,
                decision=None,
                judge=None,
                pass_threshold=cfg.pass_threshold,
                error=f"router: {exc}",
            )

        try:
            verdict = await judge_case(
                llm=judge_llm,
                signal=case.signal,
                expected_skill=case.expected_skill,
                notes=case.notes,
                actual=decision,
                model=cfg.judge_model,
            )
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            return make_case_result(
                case_id=case.id,
                signal_type=case.signal.get("type", ""),
                expected_skill=case.expected_skill,
                decision=decision,
                judge=None,
                pass_threshold=cfg.pass_threshold,
                error=f"judge: {exc}",
            )

        span.set_attribute("eval.skill_correct", verdict.skill_correct)
        span.set_attribute("eval.overall_score", verdict.overall_score)

        return make_case_result(
            case_id=case.id,
            signal_type=case.signal.get("type", ""),
            expected_skill=case.expected_skill,
            decision=decision,
            judge=verdict,
            pass_threshold=cfg.pass_threshold,
        )


async def run_suite(
    *,
    router: RouterCallable,
    judge_llm: LLMClient,
    cases: list[GoldenCase] | None = None,
    golden_path: Path = GOLDEN_SET_PATH,
    cfg: RunConfig | None = None,
) -> tuple[list[EvalCaseResult], EvalRunSummary]:
    cfg = cfg or RunConfig()
    cases = cases if cases is not None else load_cases(golden_path)

    sem = asyncio.Semaphore(cfg.concurrency)

    async def _bounded(case: GoldenCase) -> EvalCaseResult:
        async with sem:
            return await run_case(case, router=router, judge_llm=judge_llm, cfg=cfg)

    results = await asyncio.gather(*(_bounded(c) for c in cases))
    return list(results), summarize(list(results))


def summarize(results: list[EvalCaseResult]) -> EvalRunSummary:
    total = len(results)
    if total == 0:
        return EvalRunSummary(
            total=0, passed=0, pass_rate=0.0,
            mean_overall_score=0.0, mean_confidence_calibration=0.0, mean_rationale_quality=0.0,
        )
    judged = [r for r in results if r.judge is not None]
    passed = sum(1 for r in results if r.passed)

    def _mean(values: list[int]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    by_skill: dict[str, dict[str, float]] = {}
    skills = {r.expected_skill for r in results}
    for skill in skills:
        subset = [r for r in results if r.expected_skill == skill]
        subset_judged = [r for r in subset if r.judge is not None]
        sub_pass = sum(1 for r in subset if r.passed)
        by_skill[skill] = {
            "total": len(subset),
            "passed": sub_pass,
            "pass_rate": round(sub_pass / len(subset), 2) if subset else 0.0,
            "mean_overall_score": _mean([r.judge.overall_score for r in subset_judged]),
        }

    return EvalRunSummary(
        total=total,
        passed=passed,
        pass_rate=round(passed / total, 2),
        mean_overall_score=_mean([r.judge.overall_score for r in judged]),
        mean_confidence_calibration=_mean([r.judge.confidence_calibration for r in judged]),
        mean_rationale_quality=_mean([r.judge.rationale_quality for r in judged]),
        by_skill=by_skill,
    )


__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_PASS_THRESHOLD",
    "EvalCaseResult",
    "EvalRunSummary",
    "JudgeVerdict",
    "RouterCallable",
    "RunConfig",
    "fallback_chain_router",
    "run_case",
    "run_suite",
    "summarize",
]
