"""Tests for the Customer.io MCP server.

We bypass the HTTP transport and invoke registered tools directly — the tool
functions themselves are the interesting surface (sandbox guard, idempotency,
draft shape)."""
from __future__ import annotations

from typing import Any

from mcp_servers.customer_io import server as cio_server
from mcp_servers.customer_io.idempotency import IdempotencyCache


class FakeCIO:
    def __init__(self):
        self.tracks: list[dict[str, Any]] = []
        self.segments: list[dict[str, Any]] = []

    def track(self, customer_id, name, **data):
        self.tracks.append({"customer_id": customer_id, "name": name, "data": data})
        return {"ok": True}

    def add_to_segment(self, segment_id, customer_ids):
        self.segments.append({"segment_id": segment_id, "customer_ids": list(customer_ids)})
        return {"ok": True, "count": len(customer_ids)}


def _tools(mcp) -> dict[str, Any]:
    return mcp._tool_manager._tools  # noqa: SLF001


def _call(mcp, name: str, **kwargs):
    return _tools(mcp)[name].fn(**kwargs)


def test_create_campaign_draft_returns_structured_draft():
    mcp = cio_server.build_mcp_server(client=FakeCIO(), cache=IdempotencyCache())
    result = _call(
        mcp, "create_campaign_draft",
        signal_id="sig-1",
        user_id="user-aha-001",
        audience_segment="free_activated_today",
        channel="email",
        subject="You're onto something",
        body_markdown="You just wired up X and Y — try Z next.",
        call_to_action="Invite a teammate",
        rationale="aha-moment threshold crossed; invite momentum is the named next step.",
        playbook_slug="aha-moment-free-user",
    )
    assert result["signal_id"] == "sig-1"
    assert result["channel"] == "email"
    assert result["playbook_slug"] == "aha-moment-free-user"


def test_trigger_broadcast_sandbox_guard_refuses(monkeypatch):
    monkeypatch.delenv("CUSTOMERIO_SANDBOX", raising=False)
    monkeypatch.setenv("CUSTOMERIO_ENV", "sandbox")
    fake = FakeCIO()
    mcp = cio_server.build_mcp_server(client=fake, cache=IdempotencyCache())

    result = _call(mcp, "trigger_broadcast", signal_id="sig-1", user_id="u1", broadcast_name="welcome", data={"x": 1})
    assert result["ok"] is False
    assert "sandbox" in result["error"].lower()
    assert fake.tracks == []


def test_trigger_broadcast_prod_env_refuses(monkeypatch):
    monkeypatch.setenv("CUSTOMERIO_SANDBOX", "1")
    monkeypatch.setenv("CUSTOMERIO_ENV", "prod")
    fake = FakeCIO()
    mcp = cio_server.build_mcp_server(client=fake, cache=IdempotencyCache())
    result = _call(mcp, "trigger_broadcast", signal_id="sig-1", user_id="u1", broadcast_name="welcome")
    assert result["ok"] is False
    assert fake.tracks == []


def test_trigger_broadcast_sandbox_ok_and_idempotent(monkeypatch):
    monkeypatch.setenv("CUSTOMERIO_SANDBOX", "1")
    monkeypatch.setenv("CUSTOMERIO_ENV", "sandbox")
    fake = FakeCIO()
    mcp = cio_server.build_mcp_server(client=fake, cache=IdempotencyCache())

    first = _call(mcp, "trigger_broadcast", signal_id="sig-7", user_id="u7", broadcast_name="aha", data={"n": 1})
    assert first["ok"] is True
    assert first["already_seen"] is False
    assert len(fake.tracks) == 1

    # Same signal_id → cached, no new track call.
    second = _call(mcp, "trigger_broadcast", signal_id="sig-7", user_id="u7", broadcast_name="aha", data={"n": 1})
    assert second["already_seen"] is True
    assert len(fake.tracks) == 1


def test_add_to_segment_idempotent(monkeypatch):
    monkeypatch.setenv("CUSTOMERIO_SANDBOX", "1")
    monkeypatch.setenv("CUSTOMERIO_ENV", "sandbox")
    fake = FakeCIO()
    mcp = cio_server.build_mcp_server(client=fake, cache=IdempotencyCache())

    r1 = _call(mcp, "add_to_segment", signal_id="sig-9", segment_id=42, customer_ids=["u1", "u2"])
    assert r1["ok"] is True
    r2 = _call(mcp, "add_to_segment", signal_id="sig-9", segment_id=42, customer_ids=["u1", "u2"])
    assert r2["already_seen"] is True
    assert len(fake.segments) == 1


def test_get_campaign_membership_returns_empty_with_note():
    mcp = cio_server.build_mcp_server(client=FakeCIO(), cache=IdempotencyCache())
    result = _call(mcp, "get_campaign_membership", user_id="u1")
    assert result["campaigns"] == []
    assert "note" in result
