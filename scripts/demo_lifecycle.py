"""End-to-end demo of the lifecycle flow, including HITL — runs offline.

Wires:
  - real lifecycle orchestrator
  - real RAG (InMemoryVectorStore + HashEmbedder over the real 8-playbook corpus)
  - FakeMcpClient with realistic BigQuery rows, Customer.io drafts, and a
    canned HITL resolution (approved by default; set HITL_DECISION=rejected
    to see the rejected path)
  - FakeAnthropic returning a canned Sonnet synthesis

Prints the full `LifecycleOutput` as JSON. Under 1 second, zero credentials.

    python -m scripts.demo_lifecycle
    HITL_DECISION=rejected python -m scripts.demo_lifecycle
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

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

CORPUS = Path(__file__).resolve().parent.parent / "rag" / "corpus"


class _DemoMcp:
    """FakeMcpClient returning realistic BQ + CIO + Slack HITL responses."""

    def __init__(self, hitl_decision: str = "approved"):
        self._hitl_decision = hitl_decision
        self.calls: list[dict] = []

    async def call_tool(self, *, server: str, tool: str, arguments: dict) -> dict:
        self.calls.append({"server": server, "tool": tool})

        if server == "bigquery" and tool == "query":
            sql = arguments["sql"]
            if "FROM `grafanagent_demo.users`" in sql:
                return {
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
            return {
                "rows": [
                    {"event_type": "dashboard_created"},
                    {"event_type": "alert_configured"},
                    {"event_type": "integration_added"},
                    {"event_type": "invite_sent"},
                ],
                "row_count": 4,
            }

        if server == "customer-io" and tool == "get_campaign_membership":
            return {"campaigns": [], "note": "App-API not configured in demo"}
        if server == "customer-io" and tool == "create_campaign_draft":
            return dict(arguments)
        if server == "customer-io" and tool == "trigger_broadcast":
            return {"ok": True, "idempotency_key": f"cio:broadcast:{arguments['signal_id']}"}

        if server == "slack" and tool == "request_approval":
            return {"hitl_id": "hitl_demo_1", "state": "posted", "channel_id": arguments["channel_id"]}
        if server == "slack" and tool == "wait_for_approval":
            return {
                "state": self._hitl_decision,
                "decided_by": "isil",
                "decided_at": "2026-04-15T00:00:05Z",
                "draft": {},
            }
        if server == "slack" and tool == "mark_executed":
            return {"state": "executed"}

        return {}


async def main() -> None:
    decision = os.getenv("HITL_DECISION", "approved")

    embedder = HashEmbedder()
    store = InMemoryVectorStore(dim=embedder.dim)
    await ingest(embedder=embedder, store=store, corpus_dir=CORPUS)
    retriever = Retriever(embedder, store)

    synthesis = tool_use_response(
        tool_name="record_draft",
        tool_input={
            "audience_segment": "free_activated_today",
            "channel": "email",
            "subject": "You just wired the exact pattern our best teams use",
            "body_markdown": (
                "In the last hour you set up a dashboard, wired an alert, added an integration, "
                "and invited a teammate. That's the same pattern we see from teams who go on to "
                "run production monitoring here. One suggestion: share the dashboard you built "
                "so your invitee sees it on day one."
            ),
            "call_to_action": "Share your dashboard",
            "rationale": "aha-moment + invite momentum; playbook emphasises inviter recognition.",
            "playbook_slug": "aha-moment-free-user",
        },
        model="claude-sonnet-4-5",
    )
    llm = LLMClient(client=FakeAnthropic([synthesis]), agent="lifecycle")  # type: ignore[arg-type]

    mcp = _DemoMcp(hitl_decision=decision)
    hitl = HitlClient(mcp, default_channel="C-demo")
    orchestrator = LifecycleOrchestrator(llm=llm, mcp=mcp, retriever=retriever, hitl=hitl)

    task = LifecycleTask(
        signal=Signal(
            id="golden-aha-001",
            type="aha_moment_threshold",
            source="cli",
            user_id="user-aha-001",
            payload={"threshold": "4_actions_in_first_hour", "actions_taken": 4, "plan": "free"},
        ),
        decision=RoutingDecision(
            skill="lifecycle",
            confidence=0.93,
            rationale="aha-moment threshold crossed for a free user",
        ),
    )

    output = await orchestrator.run(task)
    print(json.dumps(output.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
