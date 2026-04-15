from agents.router.schemas import FallbackRung, RoutingDecision, Signal


def test_signal_defaults():
    s = Signal(id="s1", type="aha_moment_threshold", source="bigquery")
    assert s.payload == {}
    assert s.metadata == {}
    assert s.occurred_at is not None


def test_routing_decision_clamps_confidence():
    d = RoutingDecision(skill="lifecycle", confidence=0.95, rationale="obvious aha-moment")
    assert d.skill == "lifecycle"
    assert 0 <= d.confidence <= 1


def test_fallback_rung_enum_values():
    assert FallbackRung.HAIKU.value == "haiku"
    assert {r.value for r in FallbackRung} == {"haiku", "sonnet", "rule", "hitl"}
