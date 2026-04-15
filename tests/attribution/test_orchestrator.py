"""Attribution orchestrator tests — fan-out + structured-report synthesis."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agents._llm import LLMClient
from agents.attribution.orchestrator import AttributionOrchestrator
from agents.attribution.schemas import AttributionTask
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


def _task() -> AttributionTask:
    return AttributionTask(
        signal=Signal(
            id="sig-conv-001",
            type="conversion_milestone",
            source="bigquery",
            user_id="user-attr-003",
            payload={"plan_transition": "free->team", "campaign_first_touch": "q2_launch"},
        ),
        decision=RoutingDecision(
            skill="attribution",
            confidence=0.91,
            rationale="first paid conversion — attribution needed",
        ),
    )


def _report_response(confidence: str = "high"):
    return tool_use_response(
        tool_name="record_report",
        tool_input={
            "first_touch": "q2_launch",
            "last_touch": "q2_launch_retarget",
            "multi_touch": [
                {"campaign_id": "q2_launch", "channel": "email", "weight": 0.5},
                {"campaign_id": "q2_launch_retarget", "channel": "paid_search", "weight": 0.3},
                {"campaign_id": "unattributed", "channel": "unknown", "weight": 0.2},
            ],
            "top_driver_rationale": (
                "q2_launch email drove first touch and 50% of weighted credit — "
                "last-touch retarget closed the loop."
            ),
            "three_line_verdict": (
                "What worked: q2_launch email sequence. "
                "What didn't: 20% of journey is unattributed (UTM drop). "
                "What to change: add UTM discipline to retarget ads."
            ),
            "confidence": confidence,
            "recommend_rerun": False,
            "playbook_slug": "conversion-attribution-report",
        },
        model="claude-sonnet-4-5",
    )


@pytest.mark.asyncio
async def test_orchestrator_produces_report_with_weights_summing_to_one(retriever):
    routes = {
        ("bigquery", "query"): {
            "rows": [
                {"campaign_id": "evt-006", "channel": "app", "touch_at": "2026-04-12T16:42:00"}
            ],
            "row_count": 1,
        },
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_report_response()]), agent="attribution")  # type: ignore[arg-type]
    orch = AttributionOrchestrator(llm=llm, mcp=mcp, retriever=retriever)

    out = await orch.run(_task())
    assert out.report["first_touch"] == "q2_launch"
    assert out.report["confidence"] == "high"
    total = sum(m["weight"] for m in out.report["multi_touch"])
    assert 0.99 <= total <= 1.01
    assert out.enrichment.partial is False
    assert out.enrichment.conversion_context is not None
    assert out.posted_to_channel is None  # no channel configured → no post


@pytest.mark.asyncio
async def test_orchestrator_posts_to_slack_when_channel_configured(retriever):
    routes = {
        ("bigquery", "query"): {"rows": [], "row_count": 0},
        ("slack", "request_approval"): {"hitl_id": "hitl_report_1", "state": "posted"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_report_response()]), agent="attribution")  # type: ignore[arg-type]
    orch = AttributionOrchestrator(
        llm=llm, mcp=mcp, retriever=retriever, post_channel="C-revops"
    )

    out = await orch.run(_task())
    assert out.posted_to_channel == "C-revops"
    posted = [c for c in mcp.calls if c["tool"] == "request_approval"]
    assert len(posted) == 1
    assert posted[0]["args"]["channel_id"] == "C-revops"
    # No wait_for_approval — attribution is fire-and-log.
    assert not any(c["tool"] == "wait_for_approval" for c in mcp.calls)


@pytest.mark.asyncio
async def test_invalid_weights_are_rejected_by_schema(retriever):
    bad_response = tool_use_response(
        tool_name="record_report",
        tool_input={
            "first_touch": "a",
            "last_touch": "b",
            "multi_touch": [
                {"campaign_id": "a", "channel": "x", "weight": 0.4},
                {"campaign_id": "b", "channel": "y", "weight": 0.4},
            ],  # sums to 0.8 — invalid
            "top_driver_rationale": "x",
            "three_line_verdict": "a\nb\nc",
            "confidence": "low",
            "recommend_rerun": False,
            "playbook_slug": None,
        },
        model="claude-sonnet-4-5",
    )
    mcp = ScriptedMcp({("bigquery", "query"): {"rows": [], "row_count": 0}})
    llm = LLMClient(client=FakeAnthropic([bad_response]), agent="attribution")  # type: ignore[arg-type]
    orch = AttributionOrchestrator(llm=llm, mcp=mcp, retriever=retriever)
    with pytest.raises(Exception):  # LLMError wraps the ValidationError
        await orch.run(_task())
