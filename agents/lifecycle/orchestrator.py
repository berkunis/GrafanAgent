"""Lifecycle orchestrator — the parallel fan-out + synthesis pipeline.

    signal + decision
        │
        ▼
    ┌─────────── asyncio.gather ───────────┐
    │  BQ MCP: user profile + recent usage │
    │  RAG:    top-k playbook chunks       │
    │  CIO MCP: current campaign membership│
    └───────────────────────┬──────────────┘
                            │
                            ▼
                    Sonnet synthesis
                    (cached system + playbooks)
                            │
                            ▼
                 cio.create_campaign_draft
                            │
                            ▼
                    LifecycleOutput

Each leg is a span; if one leg fails the orchestrator proceeds on partial
context and annotates the trace. That way a transient MCP blip does not kill
the whole pipeline — the draft just gets safer and the alert fires.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from opentelemetry import trace

from agents._hitl import HitlClient
from agents._llm import LLMClient
from agents._mcp import McpClient
from agents.lifecycle.agent import synthesize_draft
from agents.lifecycle.schemas import (
    DraftSpec,
    Enrichment,
    LifecycleOutput,
    LifecycleTask,
    PlaybookHit,
    UserContext,
)
from observability import get_logger
from rag.retriever import Retriever

_tracer = trace.get_tracer("agents.lifecycle.orchestrator")
_log = get_logger("lifecycle")


class LifecycleOrchestrator:
    def __init__(
        self,
        *,
        llm: LLMClient,
        mcp: McpClient,
        retriever: Retriever,
        hitl: HitlClient | None = None,
        bq_dataset: str = "grafanagent_demo",
        execute_broadcast_name: str = "lifecycle_draft_approved",
    ):
        self._llm = llm
        self._mcp = mcp
        self._retriever = retriever
        self._hitl = hitl
        self._bq_dataset = bq_dataset
        self._execute_broadcast = execute_broadcast_name

    async def run(self, task: LifecycleTask) -> LifecycleOutput:
        start = time.perf_counter()
        with _tracer.start_as_current_span("lifecycle.run") as span:
            span.set_attribute("grafanagent.signal_id", task.signal.id)
            span.set_attribute("grafanagent.signal_type", task.signal.type)
            span.set_attribute("grafanagent.user_id", task.signal.user_id or "")

            enrichment = await self._enrich(task)
            span.set_attribute("lifecycle.enrichment.partial", enrichment.partial)
            span.set_attribute("lifecycle.enrichment.playbooks", [p.playbook_slug for p in enrichment.playbooks])

            draft_spec = await synthesize_draft(llm=self._llm, task=task, enrichment=enrichment)
            draft = await self._materialize_draft(task, draft_spec)

            hitl_fields: dict[str, Any] = {
                "hitl_id": None,
                "hitl_state": None,
                "hitl_decided_by": None,
                "hitl_decided_at": None,
                "executed": False,
                "execution_detail": None,
            }
            final_draft = draft

            if self._hitl is not None:
                handle = await self._hitl.request(
                    signal_id=task.signal.id,
                    draft=draft,
                    user_context=(
                        enrichment.user_context.model_dump()
                        if enrichment.user_context else None
                    ),
                )
                resolution = await self._hitl.wait(handle.hitl_id)
                hitl_fields["hitl_id"] = resolution.hitl_id
                hitl_fields["hitl_state"] = resolution.state
                hitl_fields["hitl_decided_by"] = resolution.decided_by
                hitl_fields["hitl_decided_at"] = resolution.decided_at
                # Operator edits flow back through `resolution.draft`.
                if resolution.draft:
                    final_draft = {**draft, **resolution.draft}

                if resolution.approved:
                    exec_result = await self._execute(task, final_draft)
                    hitl_fields["executed"] = bool(exec_result.get("ok"))
                    hitl_fields["execution_detail"] = exec_result
                    await self._hitl.mark_executed(
                        resolution.hitl_id,
                        by="lifecycle",
                        reason="broadcast triggered",
                    )

            latency_ms = int((time.perf_counter() - start) * 1000)
            span.set_attribute("lifecycle.latency_ms", latency_ms)
            _log.info(
                "lifecycle.drafted",
                signal_id=task.signal.id,
                audience=draft_spec.audience_segment,
                channel=draft_spec.channel,
                playbook=draft_spec.playbook_slug,
                partial=enrichment.partial,
                hitl_state=hitl_fields["hitl_state"],
                executed=hitl_fields["executed"],
                latency_ms=latency_ms,
            )

            return LifecycleOutput(
                signal_id=task.signal.id,
                enrichment=enrichment,
                draft=final_draft,
                latency_ms=latency_ms,
                **hitl_fields,
            )

    # ---------- fan-out ----------

    async def _enrich(self, task: LifecycleTask) -> Enrichment:
        """Run BQ + RAG + CIO in parallel. Log partial failures; never raise."""
        with _tracer.start_as_current_span("lifecycle.enrich"):
            user_ctx_task = asyncio.create_task(self._fetch_user_context(task))
            playbooks_task = asyncio.create_task(self._fetch_playbooks(task))
            campaigns_task = asyncio.create_task(self._fetch_current_campaigns(task))

            user_ctx, playbooks, campaigns = await asyncio.gather(
                user_ctx_task, playbooks_task, campaigns_task, return_exceptions=True
            )

            errors: dict[str, str] = {}
            uc = None
            if isinstance(user_ctx, Exception):
                errors["bigquery"] = str(user_ctx)
            else:
                uc = user_ctx

            pbs: list[PlaybookHit] = []
            if isinstance(playbooks, Exception):
                errors["rag"] = str(playbooks)
            else:
                pbs = playbooks

            camps: list[str] = []
            if isinstance(campaigns, Exception):
                errors["customer_io"] = str(campaigns)
            else:
                camps = campaigns

            return Enrichment(
                user_context=uc,
                playbooks=pbs,
                current_campaigns=camps,
                partial=bool(errors),
                errors=errors,
            )

    async def _fetch_user_context(self, task: LifecycleTask) -> UserContext | None:
        if not task.signal.user_id:
            return None
        uid = task.signal.user_id
        with _tracer.start_as_current_span("lifecycle.bq.user_context"):
            user_sql = (
                f"SELECT * FROM `{self._bq_dataset}.users` WHERE user_id = '{uid}' LIMIT 1"
            )
            usage_sql = (
                f"SELECT event_type, occurred_at FROM `{self._bq_dataset}.usage_events` "
                f"WHERE user_id = '{uid}' ORDER BY occurred_at DESC LIMIT 20"
            )
            user_rows = (await self._mcp.call_tool(
                server="bigquery",
                tool="query",
                arguments={"sql": user_sql, "max_rows": 1},
            )).get("rows", [])
            usage_rows = (await self._mcp.call_tool(
                server="bigquery",
                tool="query",
                arguments={"sql": usage_sql, "max_rows": 20},
            )).get("rows", [])

            if not user_rows:
                return UserContext(user_id=uid)
            row = user_rows[0]
            return UserContext(
                user_id=uid,
                plan=row.get("plan"),
                lifecycle_stage=row.get("lifecycle_stage"),
                company=row.get("company"),
                country=row.get("country"),
                signed_up_at=str(row.get("signed_up_at")) if row.get("signed_up_at") else None,
                recent_event_types=[r["event_type"] for r in usage_rows if "event_type" in r],
                raw_rows=user_rows,
            )

    async def _fetch_playbooks(self, task: LifecycleTask) -> list[PlaybookHit]:
        with _tracer.start_as_current_span("lifecycle.rag.retrieve"):
            query = (
                f"Signal type: {task.signal.type}. "
                f"Rationale from router: {task.decision.rationale}. "
                f"User_id: {task.signal.user_id or 'unknown'}."
            )
            hits = await self._retriever.retrieve(query, k=3)
            return [
                PlaybookHit(
                    playbook_slug=h.chunk.playbook_slug,
                    section=h.chunk.section,
                    content=h.chunk.content,
                    score=h.score,
                )
                for h in hits
            ]

    async def _fetch_current_campaigns(self, task: LifecycleTask) -> list[str]:
        if not task.signal.user_id:
            return []
        with _tracer.start_as_current_span("lifecycle.cio.current_campaigns"):
            result = await self._mcp.call_tool(
                server="customer-io",
                tool="get_campaign_membership",
                arguments={"user_id": task.signal.user_id},
            )
            campaigns = result.get("campaigns", []) or []
            return [c if isinstance(c, str) else c.get("name", "?") for c in campaigns]

    # ---------- materialize ----------

    async def _execute(self, task: LifecycleTask, draft: dict[str, Any]) -> dict[str, Any]:
        """Fire the approved draft via Customer.io. Idempotent on signal_id."""
        with _tracer.start_as_current_span("lifecycle.cio.execute"):
            return await self._mcp.call_tool(
                server="customer-io",
                tool="trigger_broadcast",
                arguments={
                    "signal_id": task.signal.id,
                    "user_id": task.signal.user_id or draft.get("user_id", "unknown"),
                    "broadcast_name": self._execute_broadcast,
                    "data": {
                        "subject": draft.get("subject"),
                        "body_markdown": draft.get("body_markdown"),
                        "call_to_action": draft.get("call_to_action"),
                        "playbook_slug": draft.get("playbook_slug"),
                        "audience_segment": draft.get("audience_segment"),
                    },
                },
            )

    async def _materialize_draft(self, task: LifecycleTask, spec: DraftSpec) -> dict[str, Any]:
        """Turn the LLM's DraftSpec into a Customer.io draft via the MCP tool.

        Going through the MCP tool (rather than constructing locally) means the
        Customer.io MCP is the single source of truth for draft shape — the
        same place that will validate on HITL approval in Phase 3.
        """
        with _tracer.start_as_current_span("lifecycle.cio.create_draft"):
            return await self._mcp.call_tool(
                server="customer-io",
                tool="create_campaign_draft",
                arguments={
                    "signal_id": task.signal.id,
                    "user_id": task.signal.user_id or "unknown",
                    "audience_segment": spec.audience_segment,
                    "channel": spec.channel,
                    "subject": spec.subject,
                    "body_markdown": spec.body_markdown,
                    "call_to_action": spec.call_to_action,
                    "rationale": spec.rationale,
                    "playbook_slug": spec.playbook_slug,
                },
            )
