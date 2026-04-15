"""HitlClient tests — request + wait + mark_executed over a FakeMcpClient."""
from __future__ import annotations

from typing import Any

import pytest

from agents._hitl import HitlClient, HitlError


class FakeMcpForHitl:
    def __init__(self, responses: dict[str, Any] | list[dict[str, Any]] | None = None):
        # Either a dict keyed by tool name (same response every call) or a list
        # of responses consumed in order.
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    async def call_tool(self, *, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"server": server, "tool": tool, "arguments": arguments})
        if isinstance(self.responses, list):
            return self.responses.pop(0)
        return self.responses.get(tool, {})


@pytest.mark.asyncio
async def test_request_returns_handle_with_hitl_id():
    mcp = FakeMcpForHitl(
        {"request_approval": {"hitl_id": "hitl_abc", "state": "posted", "channel_id": "C1"}}
    )
    hitl = HitlClient(mcp, default_channel="C1")
    handle = await hitl.request(signal_id="sig-1", draft={"subject": "x"})
    assert handle.hitl_id == "hitl_abc"
    assert handle.state == "posted"
    assert handle.channel_id == "C1"
    assert mcp.calls[0]["arguments"]["channel_id"] == "C1"
    assert mcp.calls[0]["arguments"]["signal_id"] == "sig-1"


@pytest.mark.asyncio
async def test_request_raises_without_channel():
    hitl = HitlClient(FakeMcpForHitl())
    with pytest.raises(HitlError, match="channel"):
        await hitl.request(signal_id="sig-1", draft={})


@pytest.mark.asyncio
async def test_request_raises_when_server_returns_error():
    mcp = FakeMcpForHitl({"request_approval": {"error": "boom"}})
    hitl = HitlClient(mcp, default_channel="C1")
    with pytest.raises(HitlError):
        await hitl.request(signal_id="sig-1", draft={})


@pytest.mark.asyncio
async def test_wait_returns_resolution_with_approved_flag():
    mcp = FakeMcpForHitl(
        {"wait_for_approval": {
            "state": "approved",
            "decided_by": "isil",
            "decided_at": "2026-04-15T00:00:00Z",
            "draft": {"subject": "edited subject"},
        }}
    )
    hitl = HitlClient(mcp, default_channel="C1")
    res = await hitl.wait("hitl_abc")
    assert res.approved is True
    assert res.state == "approved"
    assert res.decided_by == "isil"
    assert res.draft["subject"] == "edited subject"


@pytest.mark.asyncio
async def test_wait_returns_resolution_with_rejected():
    mcp = FakeMcpForHitl({"wait_for_approval": {"state": "rejected", "decided_by": "u1", "draft": {}}})
    hitl = HitlClient(mcp, default_channel="C1")
    res = await hitl.wait("hitl_abc")
    assert res.approved is False
    assert res.state == "rejected"


@pytest.mark.asyncio
async def test_mark_executed_calls_mcp():
    mcp = FakeMcpForHitl({"mark_executed": {"state": "executed"}})
    hitl = HitlClient(mcp, default_channel="C1")
    await hitl.mark_executed("hitl_abc", by="lifecycle")
    assert mcp.calls[0]["tool"] == "mark_executed"
    assert mcp.calls[0]["arguments"]["by"] == "lifecycle"
