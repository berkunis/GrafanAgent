"""`grafanagent trigger` — POSTs to the router with a fake HTTP sender."""
from __future__ import annotations

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from cli import _http
from cli.main import app


class FakeSender:
    def __init__(self, status_code: int = 200, body: dict[str, Any] | None = None):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.body = body or {
            "signal_id": "golden-aha-001",
            "decision": {"skill": "lifecycle", "confidence": 0.93, "rationale": "x", "payload": {}},
            "rung_used": "haiku",
            "models_consulted": ["claude-haiku-4-5"],
            "latency_ms": 7,
        }

    def post(self, url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return httpx.Response(
            status_code=self.status_code,
            content=(json_dumps(self.body) if self.status_code < 400 else b"server said no"),
            request=httpx.Request("POST", url),
            headers={"content-type": "application/json"},
        )


def json_dumps(value: Any) -> bytes:
    return json.dumps(value).encode()


def _write_signal(tmp_path) -> str:
    p = tmp_path / "signal.json"
    p.write_text(json.dumps({
        "id": "golden-aha-001",
        "type": "aha_moment_threshold",
        "source": "cli",
        "user_id": "user-aha-001",
    }))
    return str(p)


def test_trigger_prints_decision(tmp_path):
    fake = FakeSender()
    reset = _http.set_sender(fake)
    try:
        runner = CliRunner()
        r = runner.invoke(app, ["trigger", _write_signal(tmp_path), "--raw"])
        assert r.exit_code == 0, r.output
        assert "golden-aha-001" in r.output
        assert "lifecycle" in r.output
        assert fake.calls[0]["url"] == "http://localhost:8000/signal"
        assert fake.calls[0]["json"]["id"] == "golden-aha-001"
    finally:
        reset()


def test_trigger_with_custom_url(tmp_path):
    fake = FakeSender()
    reset = _http.set_sender(fake)
    try:
        runner = CliRunner()
        r = runner.invoke(
            app, ["trigger", _write_signal(tmp_path), "--url", "https://router.example.test/signal", "--raw"]
        )
        assert r.exit_code == 0
        assert fake.calls[0]["url"] == "https://router.example.test/signal"
    finally:
        reset()


def test_trigger_exits_on_http_error(tmp_path):
    fake = FakeSender(status_code=500)
    reset = _http.set_sender(fake)
    try:
        runner = CliRunner()
        r = runner.invoke(app, ["trigger", _write_signal(tmp_path)])
        assert r.exit_code == 500
    finally:
        reset()


def test_trigger_rejects_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    runner = CliRunner()
    r = runner.invoke(app, ["trigger", str(bad)])
    assert r.exit_code == 2
