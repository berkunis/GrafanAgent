"""Router FastAPI application — the entrypoint Cloud Run hits.

Single endpoint: `POST /signal`. The FallbackChain owns all the routing logic;
this module is just HTTP plumbing + OTel instrumentation of the request span.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from agents._llm import LLMClient
from agents.router.fallback import FallbackChain, FallbackConfig
from agents.router.schemas import RouterResponse, Signal
from observability import get_logger, signal_context

_tracer = trace.get_tracer("agents.router.app")


def create_app(*, chain: FallbackChain | None = None) -> FastAPI:
    """Build the FastAPI app. `chain` is injectable for tests."""
    app = FastAPI(title="grafanagent-router", version="0.1.0")
    log = get_logger("router")

    if chain is None:
        chain = FallbackChain(LLMClient(agent="router"), FallbackConfig())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "router"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready", "service": "router"}

    @app.post("/signal", response_model=RouterResponse)
    async def post_signal(signal: Signal) -> RouterResponse:
        start = time.perf_counter()
        # signal_context propagates signal_id/type onto every downstream span
        # + metric label (LLM calls, MCP calls, HITL wait) via contextvars,
        # so the dashboard can ask "what did *this* one signal cost?"
        with signal_context(signal.id, signal.type), _tracer.start_as_current_span("router.signal") as span:
            span.set_attribute("grafanagent.signal_id", signal.id)
            span.set_attribute("grafanagent.signal_type", signal.type)
            span.set_attribute("grafanagent.signal_source", signal.source)
            try:
                result = await chain.decide(signal)
            except Exception as exc:  # noqa: BLE001
                log.exception("router.error", signal_id=signal.id, error=str(exc))
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            latency_ms = int((time.perf_counter() - start) * 1000)
            span.set_attribute("grafanagent.latency_ms", latency_ms)

            log.info(
                "router.decided",
                signal_id=signal.id,
                signal_type=signal.type,
                skill=result.decision.skill,
                confidence=result.decision.confidence,
                rung=result.rung.value,
                models=result.models_consulted,
                latency_ms=latency_ms,
            )

            return RouterResponse(
                signal_id=signal.id,
                decision=result.decision,
                rung_used=result.rung,
                models_consulted=result.models_consulted,
                latency_ms=latency_ms,
            )

    FastAPIInstrumentor.instrument_app(app)
    return app
