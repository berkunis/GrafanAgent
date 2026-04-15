"""Router entrypoint. SMOKE=1 boots, emits a span, and exits — for `make smoke`
and CI. Otherwise we run the FastAPI app on $PORT (Cloud Run convention)."""
from __future__ import annotations

import os

from observability import get_logger, get_tracer, init_telemetry

SERVICE_NAME = "router"


def main() -> None:
    init_telemetry(SERVICE_NAME)
    log = get_logger(SERVICE_NAME)
    tracer = get_tracer(SERVICE_NAME)

    with tracer.start_as_current_span(f"{SERVICE_NAME}.boot"):
        log.info("agent.alive", service=SERVICE_NAME)

    if os.getenv("SMOKE") == "1":
        return

    # Defer FastAPI import until after telemetry is wired so instrumentors attach cleanly.
    import uvicorn

    from agents.router.app import create_app

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
