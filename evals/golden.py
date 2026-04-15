"""Golden-set loader + rule-table scoring (deterministic Phase 4 eval).

Phase 5 stacks an LLM-as-judge on top of this and pushes the results to Mimir
for the Grafana regression alert. For now the rule-table check catches any
signal type that's been renamed or un-mapped, which is the most common form
of regression anyway.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from agents.router.rules import rule_lookup

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.jsonl"


@dataclass(frozen=True)
class GoldenCase:
    id: str
    signal: dict
    expected_skill: str
    notes: str


@dataclass(frozen=True)
class CaseResult:
    case: GoldenCase
    actual_skill: str | None        # None = rule table didn't match
    passed: bool
    detail: str


def load_cases(path: Path = GOLDEN_SET_PATH) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
        cases.append(
            GoldenCase(
                id=row["id"],
                signal=row["signal"],
                expected_skill=row["expected_skill"],
                notes=row.get("notes", ""),
            )
        )
    return cases


def score_case(case: GoldenCase) -> CaseResult:
    signal_type = case.signal.get("type", "")
    decision = rule_lookup(signal_type)
    actual = decision.skill if decision else None
    passed = actual == case.expected_skill
    detail = (
        f"rule-table {'hit' if decision else 'miss'} — "
        f"expected={case.expected_skill}, actual={actual!r}"
    )
    return CaseResult(case=case, actual_skill=actual, passed=passed, detail=detail)


def run(path: Path = GOLDEN_SET_PATH) -> Iterator[CaseResult]:
    for case in load_cases(path):
        yield score_case(case)


def summary(results: list[CaseResult]) -> tuple[int, int, float]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    rate = passed / total if total else 0.0
    return passed, total, rate
