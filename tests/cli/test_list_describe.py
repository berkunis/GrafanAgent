"""`list` and `describe` — assert the rendered tables contain known entries."""
from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

# Rich reads COLUMNS / TERM to decide column widths — without this, long slugs
# get truncated mid-cell and substring assertions below fail.
runner = CliRunner(env={"COLUMNS": "240", "TERM": "dumb", "NO_COLOR": "1"})


def test_list_agents_includes_all_four():
    r = runner.invoke(app, ["list", "agents"])
    assert r.exit_code == 0, r.output
    for name in ("router", "lifecycle", "lead_scoring", "attribution"):
        assert name in r.output
    for mcp in ("bigquery", "customer_io", "slack"):
        assert mcp in r.output


def test_list_signals_includes_rule_table():
    r = runner.invoke(app, ["list", "signals"])
    assert r.exit_code == 0
    # Representative sample of rule-table keys.
    for key in ("aha_moment_threshold", "mql_stale", "campaign_completed"):
        assert key in r.output


def test_list_playbooks_includes_known_slugs():
    r = runner.invoke(app, ["list", "playbooks"])
    assert r.exit_code == 0
    assert "aha-moment-free-user" in r.output
    assert "trial-expiring-dormant" in r.output


def test_describe_agent_router_dumps_fallback_and_rules():
    r = runner.invoke(app, ["describe", "agent", "router"])
    assert r.exit_code == 0
    assert "fallback chain" in r.output
    assert "rule table" in r.output
    assert "aha_moment_threshold" in r.output


def test_describe_agent_lifecycle_dumps_orchestration():
    r = runner.invoke(app, ["describe", "agent", "lifecycle"])
    assert r.exit_code == 0
    assert "claude-sonnet" in r.output
    assert "RAG" in r.output or "playbooks" in r.output


def test_describe_mcp_bigquery_shows_guards():
    r = runner.invoke(app, ["describe", "mcp", "bigquery"])
    assert r.exit_code == 0
    assert "security guards" in r.output
    assert "grafanagent_demo" in r.output


def test_describe_rejects_unknown_agent():
    r = runner.invoke(app, ["describe", "agent", "does-not-exist"])
    assert r.exit_code != 0
