"""Slack MCP server — wraps the TypeScript Bolt app as MCP tools.

Tools:

- request_approval(signal_id, channel_id, draft, user_context?, timeout_s?)
    Post a draft to Slack for HITL review. Returns the initial record
    including `hitl_id`.

- get_approval_status(hitl_id)
    Return the current state + decided_by / decided_at + latest draft.

- wait_for_approval(hitl_id, timeout_ms?)
    Long-poll until the approval reaches a terminal state (approved / rejected
    / edited / timed_out / cancelled). Returns the final record.

- cancel_approval(hitl_id, reason?)
    Cancel an in-flight approval.

- mark_executed(hitl_id, by?, reason?)
    Called by the downstream agent after executing the approved action so the
    record reflects the full lifecycle (approved → executed).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

from mcp_servers.slack.client import SlackApproverClient, SlackApproverError
from observability import get_logger

_tracer = trace.get_tracer("mcp.slack")
_log = get_logger("mcp.slack")


def build_mcp_server(*, client: SlackApproverClient | None = None) -> FastMCP:
    approver = client or SlackApproverClient()
    mcp = FastMCP("grafanagent-slack")

    def _wrap(fn):
        return asyncio.get_event_loop().run_until_complete(fn) if False else fn  # readability no-op

    @mcp.tool(
        name="request_approval",
        description=(
            "Post a draft to the Slack approval app and return the initial approval "
            "record with hitl_id + state. Used by skill agents after synthesis."
        ),
    )
    async def request_approval(
        signal_id: str,
        channel_id: str,
        draft: dict[str, Any],
        user_context: dict[str, Any] | None = None,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        with _tracer.start_as_current_span("slack.request_approval") as span:
            span.set_attribute("grafanagent.signal_id", signal_id)
            span.set_attribute("slack.channel_id", channel_id)
            try:
                record = await approver.request_approval(
                    signal_id=signal_id,
                    channel_id=channel_id,
                    draft=draft,
                    user_context=user_context,
                    timeout_s=timeout_s,
                )
            except SlackApproverError as exc:
                _log.exception("slack.request_approval.failed", signal_id=signal_id)
                return {"error": str(exc)}
            span.set_attribute("hitl.id", record.get("hitl_id", ""))
            span.set_attribute("hitl.state", record.get("state", ""))
            return record

    @mcp.tool(
        name="get_approval_status",
        description="Return the current state + draft + decision metadata for an approval.",
    )
    async def get_approval_status(hitl_id: str) -> dict[str, Any]:
        with _tracer.start_as_current_span("slack.get_approval_status") as span:
            span.set_attribute("hitl.id", hitl_id)
            try:
                return await approver.get_status(hitl_id)
            except SlackApproverError as exc:
                return {"error": str(exc)}

    @mcp.tool(
        name="wait_for_approval",
        description=(
            "Long-poll the Bolt app until the approval hits a terminal state "
            "(approved/rejected/edited/timed_out/cancelled). Blocks up to timeout_ms."
        ),
    )
    async def wait_for_approval(hitl_id: str, timeout_ms: int = 300_000) -> dict[str, Any]:
        with _tracer.start_as_current_span("slack.wait_for_approval") as span:
            span.set_attribute("hitl.id", hitl_id)
            span.set_attribute("hitl.timeout_ms", timeout_ms)
            try:
                record = await approver.wait_for_approval(hitl_id, timeout_ms=timeout_ms)
            except SlackApproverError as exc:
                return {"error": str(exc)}
            span.set_attribute("hitl.state", record.get("state", ""))
            return record

    @mcp.tool(
        name="cancel_approval",
        description="Cancel an in-flight approval. Useful when a downstream dependency fails.",
    )
    async def cancel_approval(hitl_id: str, reason: str | None = None) -> dict[str, Any]:
        with _tracer.start_as_current_span("slack.cancel_approval") as span:
            span.set_attribute("hitl.id", hitl_id)
            try:
                return await approver.cancel(hitl_id, reason)
            except SlackApproverError as exc:
                return {"error": str(exc)}

    @mcp.tool(
        name="mark_executed",
        description=(
            "Mark an approved approval as executed after the downstream action completes. "
            "Gives the dashboard a definitive 'the message went out' signal."
        ),
    )
    async def mark_executed(hitl_id: str, by: str = "agent", reason: str = "") -> dict[str, Any]:
        with _tracer.start_as_current_span("slack.mark_executed") as span:
            span.set_attribute("hitl.id", hitl_id)
            try:
                return await approver.mark_executed(hitl_id, by=by, reason=reason)
            except SlackApproverError as exc:
                return {"error": str(exc)}

    return mcp


def create_app(**kwargs: Any) -> FastAPI:
    mcp = build_mcp_server(**kwargs)
    app = FastAPI(title="mcp-slack", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "server": "slack"}

    app.mount("/mcp", mcp.streamable_http_app())
    return app


def main() -> None:
    from observability import get_logger, get_tracer, init_telemetry

    init_telemetry("mcp.slack")
    log = get_logger("mcp.slack")
    tracer = get_tracer("mcp.slack")

    with tracer.start_as_current_span("mcp.slack.boot"):
        log.info(
            "mcp.alive",
            server="slack",
            tools=["request_approval", "get_approval_status", "wait_for_approval", "cancel_approval", "mark_executed"],
        )

    if os.getenv("SMOKE") == "1":
        return

    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
