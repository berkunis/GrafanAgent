"""Shared boot helper for agent services.

Each agent's main.py calls run(service_name). In SMOKE mode (env SMOKE=1) the
process emits one span and exits — handy for `make smoke` and CI. Otherwise it
boots a FastAPI server on $PORT (Cloud Run convention) with /healthz.
"""
from __future__ import annotations

import os

from fastapi import FastAPI

from observability import get_logger, get_tracer, init_telemetry


def run(service_name: str) -> None:
    init_telemetry(service_name)
    log = get_logger(service_name)
    tracer = get_tracer(service_name)

    with tracer.start_as_current_span(f"{service_name}.boot"):
        log.info("agent.alive", service=service_name)

    if os.getenv("SMOKE") == "1":
        return

    app = FastAPI(title=service_name)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
