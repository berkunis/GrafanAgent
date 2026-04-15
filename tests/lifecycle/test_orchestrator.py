"""Lifecycle orchestrator tests — parallel fan-out, partial-failure handling, synthesis."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.lifecycle.orchestrator import LifecycleOrchestrator
from agents.lifecycle.schemas import LifecycleTask
from agents.router.schemas import RoutingDecision, Signal
from rag.embeddings import HashEmbedder
from rag.ingest import ingest
from rag.retriever import Retriever
from rag.store import InMemoryVectorStore
from tests.conftest import FakeAnthropic, tool_use_response
from agents._llm import LLMClient


class FakeMcpClient:
    """Route (server, tool) → canned response; record every call."""

    def __init__(self, routes: dict[tuple[str, str], Any]):
        self._routes = dict(routes)
        self.calls: list[dict[str, Any]] = []
        self.call_order: list[tuple[str, str]] = []

    async def call_tool(
        self, *, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"server": server, "tool": tool, "args": arguments})
        self.call_order.append((server, tool))
        response = self._routes.get((server, tool))
        if callable(response):
            response = response(arguments)
        if isinstance(response, Exception):
            raise response
        # Simulate a small delay so parallel gather is observably faster than sequential.
        await asyncio.sleep(0.02)
        return response or {}


@pytest.fixture
async def retriever() -> Retriever:
    e = HashEmbedder()
    store = InMemoryVectorStore(dim=e.dim)
    from pathlib import Path

    corpus = Path(__file__).resolve().parent.parent.parent / "rag" / "corpus"
    await ingest(embedder=e, store=store, corpus_dir=corpus)
    return Retriever(e, store)


def _task() -> LifecycleTask:
    return LifecycleTask(
        signal=Signal(
            id="golden-aha-001",
            type="aha_moment_threshold",
            source="cli",
            user_id="user-aha-001",
            payload={"threshold": "4_actions_in_first_hour"},
        ),
        decision=RoutingDecision(
            skill="lifecycle",
            confidence=0.93,
            rationale="aha-moment threshold crossed for a free user",
        ),
    )


def _draft_synthesis_response():
    return tool_use_response(
        tool_name="record_draft",
        tool_input={
            "audience_segment": "free_activated_today",
            "channel": "email",
            "subject": "You just wired the exact pattern our best teams use",
            "body_markdown": (
                "Hey — in the last hour you set up a dashboard, configured an alert, "
                "added an integration, and invited a teammate. That's the same pattern we see "
                "from teams who go on to run production monitoring here. One suggestion: share "
                "the dashboard you built so your invitee sees it on day one."
            ),
            "call_to_action": "Share your dashboard",
            "rationale": "aha-moment + invite momentum; playbook emphasises inviter recognition.",
            "playbook_slug": "aha-moment-free-user",
        },
        model="claude-sonnet-4-5",
    )


def _cio_draft_response(args: dict) -> dict:
    # Mirror what the real MCP would return.
    return {**args, "playbook_slug": args.get("playbook_slug")}


@pytest.mark.asyncio
async def test_orchestrator_happy_path(retriever):
    mcp = FakeMcpClient(
        {
            ("bigquery", "query"): lambda args: (
                {
                    "rows": [
                        {
                            "user_id": "user-aha-001",
                            "plan": "free",
                            "lifecycle_stage": "activated",
                            "company": "Lattice Loop",
                            "country": "US",
                            "signed_up_at": "2026-03-12T14:01:00+00:00",
                        }
                    ],
                    "row_count": 1,
                }
                if "FROM `grafanagent_demo.users`" in args["sql"]
                else {
                    "rows": [
                        {"event_type": "dashboard_created"},
                        {"event_type": "alert_configured"},
                        {"event_type": "integration_added"},
                        {"event_type": "invite_sent"},
                    ],
                    "row_count": 4,
                }
            ),
            ("customer-io", "get_campaign_membership"): {"campaigns": []},
            ("customer-io", "create_campaign_draft"): _cio_draft_response,
        }
    )
    llm = LLMClient(client=FakeAnthropic([_draft_synthesis_response()]), agent="lifecycle")  # type: ignore[arg-type]
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever)

    out = await orch.run(_task())

    # Enrichment fan-out actually happened.
    assert out.enrichment.user_context is not None
    assert out.enrichment.user_context.plan == "free"
    assert "dashboard_created" in out.enrichment.user_context.recent_event_types
    assert out.enrichment.playbooks, "RAG returned no hits"
    assert any(p.playbook_slug == "aha-moment-free-user" for p in out.enrichment.playbooks)
    assert out.enrichment.current_campaigns == []
    assert out.enrichment.partial is False

    # Draft materialized through the CIO MCP.
    assert out.draft["signal_id"] == "golden-aha-001"
    assert out.draft["channel"] == "email"
    assert out.draft["playbook_slug"] == "aha-moment-free-user"


@pytest.mark.asyncio
async def test_orchestrator_fanout_is_parallel(retriever):
    """If fan-out were sequential we'd see ~60ms (3 × 20ms sleeps).

    asyncio.gather should land under 40ms even with scheduler jitter."""
    import time

    mcp = FakeMcpClient(
        {
            ("bigquery", "query"): {"rows": [], "row_count": 0},
            ("customer-io", "get_campaign_membership"): {"campaigns": []},
            ("customer-io", "create_campaign_draft"): _cio_draft_response,
        }
    )
    llm = LLMClient(client=FakeAnthropic([_draft_synthesis_response()]), agent="lifecycle")  # type: ignore[arg-type]
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever)

    t0 = time.perf_counter()
    await orch.run(_task())
    elapsed = time.perf_counter() - t0
    # Wide bound to avoid flake on CI — sequential would be > 0.06s for three 20ms legs.
    assert elapsed < 0.08, f"fan-out looks sequential (took {elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_orchestrator_tolerates_partial_failure(retriever):
    mcp = FakeMcpClient(
        {
            ("bigquery", "query"): RuntimeError("simulated BQ outage"),
            ("customer-io", "get_campaign_membership"): {"campaigns": ["paid-welcome"]},
            ("customer-io", "create_campaign_draft"): _cio_draft_response,
        }
    )
    llm = LLMClient(client=FakeAnthropic([_draft_synthesis_response()]), agent="lifecycle")  # type: ignore[arg-type]
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever)

    out = await orch.run(_task())
    # Degraded but not failed.
    assert out.enrichment.partial is True
    assert "bigquery" in out.enrichment.errors
    assert out.enrichment.user_context is None
    # RAG + CIO still populated.
    assert out.enrichment.playbooks
    assert out.enrichment.current_campaigns == ["paid-welcome"]
    # Draft still produced.
    assert out.draft["signal_id"] == "golden-aha-001"
