import pytest

from agents.router.classifier import classify
from agents.router.schemas import RoutingDecision, Signal
from tests.conftest import tool_use_response


@pytest.mark.asyncio
async def test_classify_returns_structured_decision(make_llm):
    llm, fake = make_llm(
        tool_use_response(
            tool_name="record_decision",
            tool_input={
                "skill": "lifecycle",
                "confidence": 0.93,
                "rationale": "aha-moment threshold crossed for a free user",
                "payload": {"user_id": "user-aha-001"},
            },
        )
    )
    decision = await classify(
        llm=llm,
        signal=Signal(id="s", type="aha_moment_threshold", source="cli"),
        model="claude-haiku-4-5",
    )
    assert isinstance(decision, RoutingDecision)
    assert decision.skill == "lifecycle"
    assert decision.confidence == 0.93

    # Verify the Anthropic call shape.
    call = fake.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["tool_choice"] == {"type": "tool", "name": "record_decision"}
    # System prompt should be wrapped with cache_control (cache_system=True).
    assert isinstance(call["system"], list)
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
