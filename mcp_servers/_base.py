"""Shared boot helper for MCP server stubs.

Real servers will be implemented with the `mcp` package's stdio/HTTP transports.
For now we keep the surface tiny: emit a boot span, log a placeholder tool, and
either exit (SMOKE=1) or block on a healthcheck server (PORT).
"""
from __future__ import annotations

import os

from fastapi import FastAPI

from observability import get_logger, get_tracer, init_telemetry


def run(server_name: str, tool_names: list[str]) -> None:
    init_telemetry(f"mcp.{server_name}")
    log = get_logger(f"mcp.{server_name}")
    tracer = get_tracer(f"mcp.{server_name}")

    with tracer.start_as_current_span(f"mcp.{server_name}.boot"):
        log.info("mcp.alive", server=server_name, tools=tool_names)

    if os.getenv("SMOKE") == "1":
        return

    app = FastAPI(title=f"mcp-{server_name}")

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "server": server_name, "tools": tool_names}

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
