"""Lead-scoring FastAPI surface."""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from agents._hitl import HitlClient
from agents._llm import LLMClient
from agents._mcp import HttpMcpClient
from agents.lead_scoring.orchestrator import LeadScoringOrchestrator
from agents.lead_scoring.schemas import LeadScoringOutput, LeadScoringTask
from rag.embeddings import VertexEmbedder
from rag.retriever import Retriever
from rag.store import PgVectorStore


def create_app(*, orchestrator: LeadScoringOrchestrator | None = None) -> FastAPI:
    app = FastAPI(title="grafanagent-lead-scoring", version="0.1.0")

    if orchestrator is None:
        embedder = VertexEmbedder()
        store = PgVectorStore(dim=embedder.dim)
        retriever = Retriever(embedder, store)
        mcp = HttpMcpClient()
        hitl = HitlClient(mcp) if os.getenv("SLACK_APPROVAL_CHANNEL") else None
        orchestrator = LeadScoringOrchestrator(
            llm=LLMClient(agent="lead_scoring"),
            mcp=mcp,
            retriever=retriever,
            hitl=hitl,
            bq_dataset=os.getenv("BQ_DATASET", "grafanagent_demo"),
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "lead_scoring"}

    @app.post("/run", response_model=LeadScoringOutput)
    async def run(task: LeadScoringTask) -> LeadScoringOutput:
        try:
            return await orchestrator.run(task)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    FastAPIInstrumentor.instrument_app(app)
    return app
