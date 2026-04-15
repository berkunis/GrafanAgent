"""Human-in-the-loop client used by every skill agent.

Agents produce a draft, hand it to `HitlClient.request(...)`, and then
`wait(...)` for a terminal state. Everything goes through the Slack MCP so the
agent does not know (or care) whether the downstream surface is Slack, Teams,
or email — swapping HITL channels is a one-line server switch later.

All calls emit OTel spans with `hitl.*` attrs. The state transitions are
authoritative in the TypeScript Bolt app's store; this client never caches.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace

from agents._mcp import McpClient
from observability import get_logger

_tracer = trace.get_tracer("agents._hitl")
_log = get_logger("hitl")


class HitlError(RuntimeError):
    pass


@dataclass(frozen=True)
class HitlHandle:
    hitl_id: str
    state: str
    channel_id: str


@dataclass(frozen=True)
class HitlResolution:
    hitl_id: str
    state: str                      # approved / rejected / edited / timed_out / cancelled
    decided_by: str | None
    decided_at: str | None
    draft: dict[str, Any]           # latest (possibly edited) draft

    @property
    def approved(self) -> bool:
        return self.state == "approved"


class HitlClient:
    def __init__(
        self,
        mcp: McpClient,
        *,
        default_channel: str | None = None,
        default_timeout_ms: int = 300_000,
        server_name: str = "slack",
    ):
        self._mcp = mcp
        self._default_channel = default_channel or os.getenv("SLACK_APPROVAL_CHANNEL", "")
        self._default_timeout_ms = default_timeout_ms
        self._server = server_name

    async def request(
        self,
        *,
        signal_id: str,
        draft: dict[str, Any],
        user_context: dict[str, Any] | None = None,
        channel_id: str | None = None,
        timeout_s: int | None = None,
    ) -> HitlHandle:
        channel = channel_id or self._default_channel
        if not channel:
            raise HitlError(
                "no Slack channel configured; set SLACK_APPROVAL_CHANNEL or pass channel_id"
            )
        with _tracer.start_as_current_span("hitl.request") as span:
            span.set_attribute("grafanagent.signal_id", signal_id)
            span.set_attribute("hitl.channel_id", channel)
            args: dict[str, Any] = {
                "signal_id": signal_id,
                "channel_id": channel,
                "draft": draft,
            }
            if user_context is not None:
                args["user_context"] = user_context
            if timeout_s is not None:
                args["timeout_s"] = timeout_s
            record = await self._mcp.call_tool(
                server=self._server, tool="request_approval", arguments=args
            )
            if "error" in record and "hitl_id" not in record:
                raise HitlError(f"Slack MCP refused request: {record['error']}")
            hitl_id = record.get("hitl_id")
            if not hitl_id:
                raise HitlError(f"request_approval returned no hitl_id: {record}")
            span.set_attribute("hitl.id", hitl_id)
            span.set_attribute("hitl.state", record.get("state", ""))
            _log.info(
                "hitl.requested",
                signal_id=signal_id,
                hitl_id=hitl_id,
                channel=channel,
                state=record.get("state"),
            )
            return HitlHandle(hitl_id=hitl_id, state=record.get("state", "posted"), channel_id=channel)

    async def wait(self, hitl_id: str, *, timeout_ms: int | None = None) -> HitlResolution:
        with _tracer.start_as_current_span("hitl.wait") as span:
            span.set_attribute("hitl.id", hitl_id)
            result = await self._mcp.call_tool(
                server=self._server,
                tool="wait_for_approval",
                arguments={"hitl_id": hitl_id, "timeout_ms": timeout_ms or self._default_timeout_ms},
            )
            if "error" in result and "state" not in result:
                raise HitlError(f"Slack MCP wait failed: {result['error']}")
            state = result.get("state") or "unknown"
            span.set_attribute("hitl.state", state)
            _log.info(
                "hitl.resolved",
                hitl_id=hitl_id,
                state=state,
                decided_by=result.get("decided_by"),
            )
            return HitlResolution(
                hitl_id=hitl_id,
                state=state,
                decided_by=result.get("decided_by"),
                decided_at=result.get("decided_at"),
                draft=result.get("draft") or {},
            )

    async def mark_executed(
        self, hitl_id: str, *, by: str = "agent", reason: str = ""
    ) -> None:
        with _tracer.start_as_current_span("hitl.mark_executed") as span:
            span.set_attribute("hitl.id", hitl_id)
            await self._mcp.call_tool(
                server=self._server,
                tool="mark_executed",
                arguments={"hitl_id": hitl_id, "by": by, "reason": reason},
            )
