"""Shared MCP client helper — agents call skills through this, not the SDK directly.

The protocol is intentionally tiny (`call_tool(server, tool, args) -> dict`).
That lets unit tests inject a `FakeMcpClient` while the production
`HttpMcpClient` talks to a real MCP streamable-HTTP endpoint. Every call gets
an OTel span so cross-service traces stitch together in Tempo.

Server URLs are resolved from env:
    MCP_BIGQUERY_URL        → http://localhost:8081/mcp
    MCP_CUSTOMER_IO_URL     → http://localhost:8082/mcp
    MCP_SLACK_URL           → http://localhost:8083/mcp  (Phase 3)
"""
from __future__ import annotations

import os
from typing import Any, Protocol

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("agents._mcp")


class McpClient(Protocol):
    async def call_tool(
        self, *, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        ...


class McpError(RuntimeError):
    ...


def _server_url(server: str) -> str:
    key = f"MCP_{server.upper().replace('-', '_')}_URL"
    url = os.getenv(key)
    if not url:
        raise McpError(f"env var {key} is not set; cannot reach MCP server '{server}'")
    return url


class HttpMcpClient:
    """Real client. Opens a short-lived streamable-HTTP session per tool call.

    For agents that make several calls to the same server in quick succession,
    upgrade to a persistent ClientSession pool — but keep the protocol stable.
    """

    async def call_tool(
        self, *, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = _server_url(server)
        with _tracer.start_as_current_span(f"mcp.{server}.{tool}") as span:
            span.set_attribute("mcp.server", server)
            span.set_attribute("mcp.tool", tool)
            span.set_attribute("mcp.server.url", url)
            try:
                async with streamablehttp_client(url) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(name=tool, arguments=arguments)
                        return _unwrap_tool_result(result)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise McpError(f"tool call failed: {server}.{tool}: {exc}") from exc


def _unwrap_tool_result(result: Any) -> dict[str, Any]:
    """MCP tool calls return `CallToolResult` with structured or text content.

    FastMCP tools that return a dict surface as `structuredContent`; string
    returns come as `TextContent` blocks. This helper flattens both to a dict.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return dict(structured) if not isinstance(structured, dict) else structured

    content = getattr(result, "content", []) or []
    if not content:
        return {}
    block = content[0]
    text = getattr(block, "text", None)
    if text is None:
        return {"raw": repr(block)}
    try:
        import json

        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {"text": text}
