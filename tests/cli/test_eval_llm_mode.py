"""CLI: --mode llm refuses without ANTHROPIC_API_KEY; rule mode still works."""
from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner(env={"COLUMNS": "240", "TERM": "dumb", "NO_COLOR": "1"})


def test_llm_mode_exits_two_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = runner.invoke(app, ["eval", "--mode", "llm"])
    assert r.exit_code == 2
    assert "ANTHROPIC_API_KEY" in r.output


def test_unknown_mode_is_rejected():
    r = runner.invoke(app, ["eval", "--mode", "nonsense"])
    assert r.exit_code != 0
    assert "expected 'rule' or 'llm'" in r.output
