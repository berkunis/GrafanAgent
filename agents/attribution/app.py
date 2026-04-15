"""Attribution FastAPI surface."""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from agents._llm import LLMClient
from agents._mcp import HttpMcpClient
from agents.attribution.orchestrator import AttributionOrchestrator
from agents.attribution.schemas import AttributionOutput, AttributionTask
from rag.embeddings import VertexEmbedder
from rag.retriever import Retriever
from rag.store import PgVectorStore


def create_app(*, orchestrator: AttributionOrchestrator | None = None) -> FastAPI:
    app = FastAPI(title="grafanagent-attribution", version="0.1.0")

    if orchestrator is None:
        embedder = VertexEmbedder()
        store = PgVectorStore(dim=embedder.dim)
        retriever = Retriever(embedder, store)
        orchestrator = AttributionOrchestrator(
            llm=LLMClient(agent="attribution"),
            mcp=HttpMcpClient(),
            retriever=retriever,
            bq_dataset=os.getenv("BQ_DATASET", "grafanagent_demo"),
            post_channel=os.getenv("ATTRIBUTION_POST_CHANNEL", ""),
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "attribution"}

    @app.post("/run", response_model=AttributionOutput)
    async def run(task: AttributionTask) -> AttributionOutput:
        try:
            return await orchestrator.run(task)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    FastAPIInstrumentor.instrument_app(app)
    return app
