"""LLM judge tests — FakeAnthropic-backed so no API traffic."""
from __future__ import annotations

import pytest

from agents.router.schemas import RoutingDecision
from evals.judge import judge_case
from evals.schemas import JudgeVerdict
from tests.conftest import tool_use_response


@pytest.mark.asyncio
async def test_judge_returns_verdict(make_llm):
    llm, fake = make_llm(
        tool_use_response(
            tool_name="record_verdict",
            tool_input={
                "skill_correct": True,
                "confidence_calibration": 5,
                "rationale_quality": 4,
                "overall_score": 5,
                "issues": [],
            },
            model="claude-sonnet-4-5",
        )
    )
    actual = RoutingDecision(
        skill="lifecycle", confidence=0.93, rationale="aha-moment crossed for free user",
    )
    verdict = await judge_case(
        llm=llm,
        signal={"id": "s1", "type": "aha_moment_threshold"},
        expected_skill="lifecycle",
        notes="aha-moment after first-hour activation",
        actual=actual,
    )
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.skill_correct is True
    assert verdict.overall_score == 5

    call = fake.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_verdict"}
    # System prompt is cached.
    assert isinstance(call["system"], list)
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_judge_flags_wrong_skill(make_llm):
    llm, _ = make_llm(
        tool_use_response(
            tool_name="record_verdict",
            tool_input={
                "skill_correct": False,
                "confidence_calibration": 1,
                "rationale_quality": 2,
                "overall_score": 1,
                "issues": [
                    "picked lifecycle for an attribution question",
                    "confidence too high given mismatch",
                ],
            },
            model="claude-sonnet-4-5",
        )
    )
    actual = RoutingDecision(
        skill="lifecycle", confidence=0.88, rationale="looks lifecycle-y",
    )
    verdict = await judge_case(
        llm=llm,
        signal={"id": "s2", "type": "channel_attribution_q"},
        expected_skill="attribution",
        notes="revops asked about Q2 last-touch",
        actual=actual,
    )
    assert verdict.skill_correct is False
    assert verdict.overall_score == 1
    assert len(verdict.issues) == 2
