"""`grafanagent eval` — real golden set + synthetic failure case."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from cli.main import app
from evals.golden import GOLDEN_SET_PATH, run, summary

runner = CliRunner()


def test_shipped_golden_set_is_100_percent():
    """The repo's golden set is expected to be perfectly covered by the rule table —
    any drift shows up here before it ships."""
    results = list(run(GOLDEN_SET_PATH))
    passed, total, rate = summary(results)
    assert total == 10
    assert passed == total
    assert rate == 1.0


def test_eval_command_exits_zero_on_shipped_set():
    r = runner.invoke(app, ["eval"])
    assert r.exit_code == 0, r.output
    assert "pass rate" in r.output


def test_eval_exits_nonzero_on_rule_miss(tmp_path):
    bad = tmp_path / "golden.jsonl"
    bad.write_text(json.dumps({
        "id": "fake-1",
        "expected_skill": "lifecycle",
        "signal": {"id": "fake", "type": "totally_unknown_signal_type", "source": "cli"},
        "notes": "",
    }) + "\n")
    r = runner.invoke(app, ["eval", "--golden-set", str(bad), "--threshold", "0.99"])
    assert r.exit_code == 1
    assert "FAIL" in r.output


def test_eval_bad_file_exits_two(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"
    r = runner.invoke(app, ["eval", "--golden-set", str(missing)])
    assert r.exit_code == 2
