"""OTel metric emission for eval runs.

Every metric is tagged with `eval.set` (golden-set name) and `eval.mode`
(rule or llm) so the Grafana dashboard can chart them separately and the
alert rule scopes cleanly.

Metrics:
    grafanagent_eval_cases_total{set, mode, outcome=pass|fail}
    grafanagent_eval_pass_rate{set, mode}
    grafanagent_eval_judge_score{set, mode, dimension=overall|confidence|rationale}
    grafanagent_eval_per_skill_pass_rate{set, mode, skill}

Works offline via the stdout exporter (already wired by `init_telemetry`).
With `OTEL_EXPORTER_OTLP_ENDPOINT` set, metrics flow to Grafana Cloud
Mimir and become alertable.
"""
from __future__ import annotations

from opentelemetry import metrics

from evals.schemas import EvalCaseResult, EvalRunSummary

_meter = metrics.get_meter("evals")

_case_counter = _meter.create_counter(
    "grafanagent_eval_cases_total",
    description="Count of golden-set cases scored, by outcome.",
)
_pass_rate_gauge = _meter.create_gauge(
    "grafanagent_eval_pass_rate",
    description="Fraction of golden-set cases that passed this run.",
)
_judge_score_gauge = _meter.create_gauge(
    "grafanagent_eval_judge_score",
    description="Mean judge score by dimension (overall, confidence, rationale).",
)
_per_skill_gauge = _meter.create_gauge(
    "grafanagent_eval_per_skill_pass_rate",
    description="Pass rate split by expected skill.",
)


def emit(
    *,
    results: list[EvalCaseResult],
    summary: EvalRunSummary,
    set_name: str,
    mode: str,
) -> None:
    """Push every metric for one run. Call exactly once per suite invocation."""
    attrs = {"set": set_name, "mode": mode}

    for r in results:
        _case_counter.add(
            1,
            {
                **attrs,
                "outcome": "pass" if r.passed else "fail",
                "skill": r.expected_skill,
            },
        )

    _pass_rate_gauge.set(summary.pass_rate, attrs)
    _judge_score_gauge.set(summary.mean_overall_score, {**attrs, "dimension": "overall"})
    _judge_score_gauge.set(
        summary.mean_confidence_calibration, {**attrs, "dimension": "confidence"}
    )
    _judge_score_gauge.set(
        summary.mean_rationale_quality, {**attrs, "dimension": "rationale"}
    )

    for skill, stats in summary.by_skill.items():
        _per_skill_gauge.set(
            stats["pass_rate"], {**attrs, "skill": skill}
        )
