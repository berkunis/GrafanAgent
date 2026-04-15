from agents.router.rules import RULE_TABLE, rule_lookup


def test_known_signal_maps_to_skill():
    d = rule_lookup("aha_moment_threshold")
    assert d is not None
    assert d.skill == "lifecycle"
    assert d.confidence == 1.0


def test_unknown_signal_returns_none():
    assert rule_lookup("something_brand_new") is None


def test_every_rule_points_at_a_real_skill():
    assert set(RULE_TABLE.values()) <= {"lifecycle", "lead_scoring", "attribution"}
