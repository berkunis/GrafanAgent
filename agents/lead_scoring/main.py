from __future__ import annotations

import os

from observability import get_logger, get_tracer, init_telemetry

SERVICE_NAME = "lead_scoring"


def main() -> None:
    init_telemetry(SERVICE_NAME)
    log = get_logger(SERVICE_NAME)
    tracer = get_tracer(SERVICE_NAME)

    with tracer.start_as_current_span(f"{SERVICE_NAME}.boot"):
        log.info("agent.alive", service=SERVICE_NAME)

    if os.getenv("SMOKE") == "1":
        return

    import uvicorn

    from agents.lead_scoring.app import create_app

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
