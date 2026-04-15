"""Dashboard + alerts JSON sanity — schema valid + panels reference real metrics."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Metric / attribute names GrafanAgent actually emits. Keep in sync with:
#   agents/_llm.py  (instrument names)
#   agents/router/fallback.py
#   evals/metrics.py
EMITTED_METRICS = {
    "grafanagent_llm_tokens_total",
    "grafanagent_llm_cost_usd_total",
    "grafanagent_llm_calls_total",
    "grafanagent_llm_latency_seconds",
    "grafanagent_llm_latency_seconds_bucket",
    "grafanagent_signal_cost_usd_total",
    "grafanagent_router_rung_total",
    "grafanagent_eval_pass_rate",
    "grafanagent_eval_judge_score",
    "grafanagent_eval_per_skill_pass_rate",
    "grafanagent_eval_cases_total",
}


def _all_exprs(obj, acc: list[str]) -> None:
    """Recursively collect every `expr` string from a dashboard / alerts JSON tree."""
    if isinstance(obj, dict):
        if "expr" in obj and isinstance(obj["expr"], str):
            acc.append(obj["expr"])
        for v in obj.values():
            _all_exprs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _all_exprs(v, acc)


def test_dashboard_is_valid_json():
    path = ROOT / "dashboards" / "grafanagent.json"
    data = json.loads(path.read_text())
    assert data["uid"] == "grafanagent-overview"
    assert isinstance(data.get("panels"), list)
    assert len(data["panels"]) >= 10


def test_every_dashboard_expr_references_an_emitted_metric():
    path = ROOT / "dashboards" / "grafanagent.json"
    data = json.loads(path.read_text())
    exprs: list[str] = []
    _all_exprs(data, exprs)
    assert exprs, "dashboard has no PromQL expressions"
    for expr in exprs:
        assert any(m in expr for m in EMITTED_METRICS), (
            f"expr references no known emitted metric: {expr}"
        )


def test_alerts_is_valid_json_with_required_rules():
    path = ROOT / "dashboards" / "alerts.json"
    data = json.loads(path.read_text())
    titles = {
        rule["title"]
        for group in data["groups"]
        for rule in group["rules"]
    }
    # Phase 5 + Phase 6 alerts we must keep shipping.
    assert "GrafanAgent golden-set pass-rate regression" in titles
    assert "GrafanAgent LLM cost spike" in titles
    assert "GrafanAgent LLM p95 latency > 5s" in titles
    assert "GrafanAgent LLM call error rate > 5%" in titles
    assert "GrafanAgent HITL escalations spiked" in titles


def test_every_alert_expr_references_an_emitted_metric():
    path = ROOT / "dashboards" / "alerts.json"
    data = json.loads(path.read_text())
    exprs: list[str] = []
    _all_exprs(data, exprs)
    for expr in exprs:
        # Skip pure expressions on prior refs (`expression: "pass_rate"` etc)
        if not any(c in expr for c in "({_"):
            continue
        assert any(m in expr for m in EMITTED_METRICS), (
            f"alert expr references no known emitted metric: {expr}"
        )


def test_every_alert_has_a_runbook_url_or_is_explicitly_empty():
    path = ROOT / "dashboards" / "alerts.json"
    data = json.loads(path.read_text())
    for group in data["groups"]:
        for rule in group["rules"]:
            annotations = rule.get("annotations", {})
            # Pass-rate + case-failures alerts already point at the runbook. We
            # require a runbook for anything on the `runtime` group so pager
            # alerts always have a one-click resolution path.
            if group["name"] == "grafanagent-runtime":
                assert "runbook_url" in annotations, f"{rule['title']} missing runbook_url"
