"""Lead-scoring orchestrator tests — fan-out + priority-conditioned execution."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agents._hitl import HitlClient
from agents._llm import LLMClient
from agents.lead_scoring.orchestrator import LeadScoringOrchestrator
from agents.lead_scoring.schemas import LeadScoringTask
from agents.router.schemas import RoutingDecision, Signal
from rag.embeddings import HashEmbedder
from rag.ingest import ingest
from rag.retriever import Retriever
from rag.store import InMemoryVectorStore
from tests.conftest import FakeAnthropic, tool_use_response


class ScriptedMcp:
    def __init__(self, routes: dict[tuple[str, str], Any]):
        self._routes = dict(routes)
        self.calls: list[dict[str, Any]] = []

    async def call_tool(self, *, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"server": server, "tool": tool, "args": arguments})
        resp = self._routes.get((server, tool))
        if callable(resp):
            resp = resp(arguments)
        if isinstance(resp, Exception):
            raise resp
        await asyncio.sleep(0)
        return resp or {}


@pytest.fixture
async def retriever() -> Retriever:
    e = HashEmbedder()
    store = InMemoryVectorStore(dim=e.dim)
    corpus = Path(__file__).resolve().parent.parent.parent / "rag" / "corpus"
    await ingest(embedder=e, store=store, corpus_dir=corpus)
    return Retriever(e, store)


def _task(
    signal_type: str = "mql_stale",
    user_id: str = "user-mql-002",
    payload: dict | None = None,
) -> LeadScoringTask:
    return LeadScoringTask(
        signal=Signal(
            id=f"sig-{signal_type}",
            type=signal_type,
            source="bigquery",
            user_id=user_id,
            payload=payload or {"score": 74, "days_since_last_touch": 42, "intent_score": 82},
        ),
        decision=RoutingDecision(
            skill="lead_scoring",
            confidence=0.9,
            rationale=f"rule-table: {signal_type} → lead_scoring",
        ),
    )


def _score_response(priority: str, fit_score: int = 88):
    return tool_use_response(
        tool_name="record_score",
        tool_input={
            "fit_score": fit_score,
            "priority": priority,
            "top_drivers": [
                "intent-data composite 82 (high)",
                "work-email domain classifies as enterprise",
                "three integrations configured in 48h",
            ],
            "recommended_action": (
                "Same-day SDR handoff via #enterprise-pod with scoring rationale"
                if priority == "high"
                else "Queue for tier-2 outbound next business day"
                if priority == "medium"
                else "Downgrade to nurture drip; do not ping a human"
            ),
            "rationale": "aligned with enterprise-signal-sdr playbook weights",
            "playbook_slug": "enterprise-signal-sdr",
        },
        model="claude-sonnet-4-5",
    )


def _bq_routes():
    return {
        ("bigquery", "query"): lambda args: (
            {
                "rows": [
                    {
                        "user_id": "user-mql-002",
                        "email": "amir.koroma@northfold.test",
                        "company": "NorthFold Inc",
                        "plan": "free",
                        "lifecycle_stage": "mql",
                    }
                ],
                "row_count": 1,
            }
            if "FROM `grafanagent_demo.users`" in args["sql"]
            else {"rows": [{"event_type": "docs_visit"}], "row_count": 1}
        ),
    }


@pytest.mark.asyncio
async def test_high_priority_score_goes_through_hitl_and_executes(retriever):
    routes = _bq_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_ls_1", "state": "posted"},
        ("slack", "wait_for_approval"): {
            "state": "approved",
            "decided_by": "isil",
            "decided_at": "2026-04-15T12:00:00Z",
            "draft": {},
        },
        ("slack", "mark_executed"): {"state": "executed"},
        ("customer-io", "trigger_broadcast"): {"ok": True, "idempotency_key": "cio:alert"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_score_response("high")]), agent="lead_scoring")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-sdr")
    orch = LeadScoringOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.score["priority"] == "high"
    assert out.hitl_state == "approved"
    assert out.executed is True
    # SDR broadcast fired.
    broadcasts = [c for c in mcp.calls if c["tool"] == "trigger_broadcast"]
    assert len(broadcasts) == 1


@pytest.mark.asyncio
async def test_medium_priority_skips_hitl_fires_directly(retriever):
    routes = _bq_routes() | {
        ("customer-io", "trigger_broadcast"): {"ok": True, "idempotency_key": "cio:alert"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_score_response("medium", fit_score=65)]), agent="lead_scoring")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-sdr")
    orch = LeadScoringOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.score["priority"] == "medium"
    # No HITL interaction.
    assert out.hitl_id is None
    assert not any(c["tool"] == "wait_for_approval" for c in mcp.calls)
    assert out.executed is True
    # Broadcast still fired.
    assert any(c["tool"] == "trigger_broadcast" for c in mcp.calls)


@pytest.mark.asyncio
async def test_low_priority_does_not_execute(retriever):
    routes = _bq_routes()
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_score_response("low", fit_score=22)]), agent="lead_scoring")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-sdr")
    orch = LeadScoringOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.score["priority"] == "low"
    assert out.executed is False
    assert not any(c["tool"] == "trigger_broadcast" for c in mcp.calls)
    assert not any(c["tool"] == "wait_for_approval" for c in mcp.calls)


@pytest.mark.asyncio
async def test_rejected_high_priority_does_not_fire(retriever):
    routes = _bq_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_ls_reject", "state": "posted"},
        ("slack", "wait_for_approval"): {"state": "rejected", "decided_by": "ryan"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_score_response("high")]), agent="lead_scoring")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-sdr")
    orch = LeadScoringOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.hitl_state == "rejected"
    assert out.executed is False
    assert not any(c["tool"] == "trigger_broadcast" for c in mcp.calls)
    assert not any(c["tool"] == "mark_executed" for c in mcp.calls)


@pytest.mark.asyncio
async def test_bq_failure_marks_enrichment_partial(retriever):
    routes = {
        ("bigquery", "query"): RuntimeError("bq blew up"),
        ("customer-io", "trigger_broadcast"): {"ok": True, "idempotency_key": "cio:alert"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_score_response("medium")]), agent="lead_scoring")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-sdr")
    orch = LeadScoringOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.enrichment.partial is True
    assert "bigquery" in out.enrichment.errors
    # RAG still produced hits even though BQ failed.
    assert out.enrichment.playbooks
