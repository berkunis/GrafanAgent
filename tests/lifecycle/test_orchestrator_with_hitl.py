"""Lifecycle orchestrator with the HITL gate wired in.

Every path through the state machine:
    approved → CIO broadcast fires + mark_executed called + executed=True
    rejected → no CIO broadcast, executed=False
    timed_out → no CIO broadcast, executed=False
    edited+approved → final draft reflects the operator's edits
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agents._hitl import HitlClient
from agents._llm import LLMClient
from agents.lifecycle.orchestrator import LifecycleOrchestrator
from agents.lifecycle.schemas import LifecycleTask
from agents.router.schemas import RoutingDecision, Signal
from rag.embeddings import HashEmbedder
from rag.ingest import ingest
from rag.retriever import Retriever
from rag.store import InMemoryVectorStore
from tests.conftest import FakeAnthropic, tool_use_response


class ScriptedMcp:
    """Routes (server, tool) → canned response (dict or callable(args)->dict)."""

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


def _task() -> LifecycleTask:
    return LifecycleTask(
        signal=Signal(id="sig-1", type="aha_moment_threshold", source="cli", user_id="user-aha-001"),
        decision=RoutingDecision(skill="lifecycle", confidence=0.93, rationale="aha-moment"),
    )


def _synthesis():
    return tool_use_response(
        tool_name="record_draft",
        tool_input={
            "audience_segment": "free_activated_today",
            "channel": "email",
            "subject": "You're onto something",
            "body_markdown": "body text here",
            "call_to_action": "Share",
            "rationale": "aha-moment",
            "playbook_slug": "aha-moment-free-user",
        },
        model="claude-sonnet-4-5",
    )


def _enrichment_routes():
    return {
        ("bigquery", "query"): {"rows": [{"user_id": "user-aha-001", "plan": "free", "lifecycle_stage": "activated"}], "row_count": 1},
        ("customer-io", "get_campaign_membership"): {"campaigns": []},
        ("customer-io", "create_campaign_draft"): lambda args: dict(args),
    }


@pytest.mark.asyncio
async def test_hitl_approved_triggers_execution(retriever):
    routes = _enrichment_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_1", "state": "posted"},
        ("slack", "wait_for_approval"): {
            "state": "approved",
            "decided_by": "isil",
            "decided_at": "2026-04-15T00:00:00Z",
            "draft": {},  # no edits
        },
        ("slack", "mark_executed"): {"state": "executed"},
        ("customer-io", "trigger_broadcast"): {"ok": True, "idempotency_key": "cio:x:sig-1"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_synthesis()]), agent="lifecycle")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C-approvals")
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.hitl_state == "approved"
    assert out.executed is True
    assert out.execution_detail and out.execution_detail.get("ok") is True
    # Verify the CIO broadcast tool was actually called.
    broadcast_calls = [c for c in mcp.calls if c["tool"] == "trigger_broadcast"]
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["args"]["signal_id"] == "sig-1"
    # And mark_executed afterward.
    assert any(c["tool"] == "mark_executed" for c in mcp.calls)


@pytest.mark.asyncio
async def test_hitl_rejected_skips_execution(retriever):
    routes = _enrichment_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_2", "state": "posted"},
        ("slack", "wait_for_approval"): {"state": "rejected", "decided_by": "ryan"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_synthesis()]), agent="lifecycle")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C")
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.hitl_state == "rejected"
    assert out.executed is False
    assert not any(c["tool"] == "trigger_broadcast" for c in mcp.calls)
    assert not any(c["tool"] == "mark_executed" for c in mcp.calls)


@pytest.mark.asyncio
async def test_hitl_timed_out_skips_execution(retriever):
    routes = _enrichment_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_3", "state": "posted"},
        ("slack", "wait_for_approval"): {"state": "timed_out"},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_synthesis()]), agent="lifecycle")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C")
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.hitl_state == "timed_out"
    assert out.executed is False


@pytest.mark.asyncio
async def test_operator_edits_flow_into_execution_payload(retriever):
    edited_subject = "Edited by operator before send"
    routes = _enrichment_routes() | {
        ("slack", "request_approval"): {"hitl_id": "hitl_4", "state": "posted"},
        ("slack", "wait_for_approval"): {
            "state": "approved",
            "decided_by": "ryan",
            "draft": {"subject": edited_subject},
        },
        ("slack", "mark_executed"): {"state": "executed"},
        ("customer-io", "trigger_broadcast"): lambda args: {"ok": True, "args": args},
    }
    mcp = ScriptedMcp(routes)
    llm = LLMClient(client=FakeAnthropic([_synthesis()]), agent="lifecycle")  # type: ignore[arg-type]
    hitl = HitlClient(mcp, default_channel="C")
    orch = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    out = await orch.run(_task())
    assert out.hitl_state == "approved"
    assert out.draft["subject"] == edited_subject
    # The CIO call received the edited subject.
    broadcast = [c for c in mcp.calls if c["tool"] == "trigger_broadcast"][0]
    assert broadcast["args"]["data"]["subject"] == edited_subject
