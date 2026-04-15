"""Slack MCP server tests — verify tools delegate to the approver client shape."""
from __future__ import annotations

from typing import Any

import pytest

from mcp_servers.slack import server as slack_mcp


class FakeApprover:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def request_approval(self, **kwargs):
        self.calls.append(("request_approval", kwargs))
        return {"hitl_id": "hitl_fake", "state": "posted", **kwargs}

    async def get_status(self, hitl_id):
        self.calls.append(("get_status", {"hitl_id": hitl_id}))
        return {"hitl_id": hitl_id, "state": "posted"}

    async def wait_for_approval(self, hitl_id, *, timeout_ms):
        self.calls.append(("wait", {"hitl_id": hitl_id, "timeout_ms": timeout_ms}))
        return {"hitl_id": hitl_id, "state": "approved", "decided_by": "u1"}

    async def cancel(self, hitl_id, reason=None):
        self.calls.append(("cancel", {"hitl_id": hitl_id, "reason": reason}))
        return {"hitl_id": hitl_id, "state": "cancelled"}

    async def mark_executed(self, hitl_id, *, by="agent", reason=""):
        self.calls.append(("executed", {"hitl_id": hitl_id, "by": by, "reason": reason}))
        return {"hitl_id": hitl_id, "state": "executed"}


def _tools(mcp):
    return mcp._tool_manager._tools  # noqa: SLF001


async def _call(mcp, name, **kwargs):
    return await _tools(mcp)[name].fn(**kwargs)


@pytest.mark.asyncio
async def test_request_approval_delegates():
    approver = FakeApprover()
    mcp = slack_mcp.build_mcp_server(client=approver)
    result = await _call(
        mcp, "request_approval",
        signal_id="sig-1",
        channel_id="C1",
        draft={"subject": "x"},
    )
    assert result["hitl_id"] == "hitl_fake"
    assert approver.calls[0][0] == "request_approval"
    assert approver.calls[0][1]["signal_id"] == "sig-1"


@pytest.mark.asyncio
async def test_wait_for_approval_delegates():
    approver = FakeApprover()
    mcp = slack_mcp.build_mcp_server(client=approver)
    result = await _call(mcp, "wait_for_approval", hitl_id="hitl_fake", timeout_ms=50_000)
    assert result["state"] == "approved"


@pytest.mark.asyncio
async def test_mark_executed_delegates():
    approver = FakeApprover()
    mcp = slack_mcp.build_mcp_server(client=approver)
    result = await _call(mcp, "mark_executed", hitl_id="hitl_fake", by="lifecycle")
    assert result["state"] == "executed"
    assert approver.calls[0][1]["by"] == "lifecycle"


@pytest.mark.asyncio
async def test_errors_are_returned_not_raised():
    class BrokenApprover(FakeApprover):
        async def request_approval(self, **kwargs):
            from mcp_servers.slack.client import SlackApproverError
            raise SlackApproverError("upstream 500")

    mcp = slack_mcp.build_mcp_server(client=BrokenApprover())
    result = await _call(
        mcp, "request_approval", signal_id="x", channel_id="C", draft={},
    )
    assert "error" in result
    assert "upstream 500" in result["error"]
