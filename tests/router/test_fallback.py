import pytest

from agents.router.fallback import FallbackChain, FallbackConfig
from agents.router.schemas import FallbackRung, Signal
from tests.conftest import tool_use_response


def _signal(signal_type: str = "aha_moment_threshold") -> Signal:
    return Signal(id=f"s-{signal_type}", type=signal_type, source="cli")


@pytest.mark.asyncio
async def test_haiku_high_confidence_short_circuits(make_llm):
    llm, fake = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.92,
                "rationale": "clear aha-moment",
                "payload": {},
            },
        )
    )
    chain = FallbackChain(llm, FallbackConfig())
    result = await chain.decide(_signal())
    assert result.rung == FallbackRung.HAIKU
    assert result.decision.skill == "lifecycle"
    assert len(fake.calls) == 1  # Sonnet never consulted


@pytest.mark.asyncio
async def test_mid_confidence_escalates_to_sonnet(make_llm):
    llm, fake = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.62,  # middle band → Sonnet
                "rationale": "maybe lifecycle",
                "payload": {},
            },
            model="claude-haiku-4-5",
        ),
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.88,
                "rationale": "confirmed lifecycle",
                "payload": {},
            },
            model="claude-sonnet-4-5",
        ),
    )
    chain = FallbackChain(llm, FallbackConfig())
    result = await chain.decide(_signal())
    assert result.rung == FallbackRung.SONNET
    assert result.decision.skill == "lifecycle"
    assert len(fake.calls) == 2
    assert result.models_consulted == ["claude-haiku-4-5", "claude-sonnet-4-5"]


@pytest.mark.asyncio
async def test_sonnet_disagreement_uses_sonnet_choice(make_llm):
    llm, _ = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.55,
                "rationale": "looks lifecycle",
                "payload": {},
            },
            model="claude-haiku-4-5",
        ),
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lead_scoring",
                "confidence": 0.81,
                "rationale": "actually a lead-qualification question",
                "payload": {},
            },
            model="claude-sonnet-4-5",
        ),
    )
    chain = FallbackChain(llm, FallbackConfig())
    result = await chain.decide(_signal())
    assert result.rung == FallbackRung.SONNET
    assert result.decision.skill == "lead_scoring"  # Sonnet overrides


@pytest.mark.asyncio
async def test_both_low_confidence_falls_to_rule(make_llm):
    llm, _ = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.3,
                "rationale": "very uncertain",
                "payload": {},
            },
        ),
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.35,
                "rationale": "still uncertain",
                "payload": {},
            },
            model="claude-sonnet-4-5",
        ),
    )
    chain = FallbackChain(llm, FallbackConfig())
    result = await chain.decide(_signal("aha_moment_threshold"))
    assert result.rung == FallbackRung.RULE
    assert result.decision.skill == "lifecycle"
    assert result.decision.confidence == 1.0


@pytest.mark.asyncio
async def test_unknown_signal_with_low_confidence_goes_to_hitl(make_llm):
    llm, _ = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "hitl",
                "confidence": 0.2,
                "rationale": "no idea",
                "payload": {},
            },
        ),
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "hitl",
                "confidence": 0.25,
                "rationale": "also no idea",
                "payload": {},
            },
            model="claude-sonnet-4-5",
        ),
    )
    chain = FallbackChain(llm, FallbackConfig())
    result = await chain.decide(_signal("brand_new_signal_type"))
    assert result.rung == FallbackRung.HITL
    assert result.decision.skill == "hitl"
    assert "haiku" in result.decision.payload
