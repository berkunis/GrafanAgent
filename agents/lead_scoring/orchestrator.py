"""Lead-scoring orchestrator — fan-out + Sonnet scoring + conditional HITL.

Structure mirrors the lifecycle orchestrator so a reader who understands
one understands both. Differences:

  - Only two fan-out legs (BQ + RAG) — lead scoring does not need a
    Customer.io lookup.
  - HITL gates only the SDR Slack post for `priority="high"`. Medium and
    low priorities write to the CRM (or nurture queue) without a human
    gate — the playbook explicitly says "do not ping a human" for low.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from opentelemetry import trace

from agents._hitl import HitlClient
from agents._llm import LLMClient
from agents._mcp import McpClient
from agents.lead_scoring.agent import synthesize_score
from agents.lead_scoring.schemas import (
    Enrichment,
    LeadContext,
    LeadScore,
    LeadScoringOutput,
    LeadScoringTask,
    PlaybookHit,
)
from observability import get_logger, signal_context
from rag.retriever import Retriever

_tracer = trace.get_tracer("agents.lead_scoring.orchestrator")
_log = get_logger("lead_scoring")


class LeadScoringOrchestrator:
    def __init__(
        self,
        *,
        llm: LLMClient,
        mcp: McpClient,
        retriever: Retriever,
        hitl: HitlClient | None = None,
        bq_dataset: str = "grafanagent_demo",
        sdr_broadcast_name: str = "lead_scoring_high_priority",
    ):
        self._llm = llm
        self._mcp = mcp
        self._retriever = retriever
        self._hitl = hitl
        self._bq_dataset = bq_dataset
        self._sdr_broadcast = sdr_broadcast_name

    async def run(self, task: LeadScoringTask) -> LeadScoringOutput:
        start = time.perf_counter()
        with (
            signal_context(task.signal.id, task.signal.type),
            _tracer.start_as_current_span("lead_scoring.run") as span,
        ):
            span.set_attribute("grafanagent.signal_id", task.signal.id)
            span.set_attribute("grafanagent.signal_type", task.signal.type)

            enrichment = await self._enrich(task)
            span.set_attribute("lead_scoring.enrichment.partial", enrichment.partial)
            span.set_attribute(
                "lead_scoring.enrichment.playbooks",
                [p.playbook_slug for p in enrichment.playbooks],
            )

            score = await synthesize_score(llm=self._llm, task=task, enrichment=enrichment)
            span.set_attribute("lead_scoring.priority", score.priority)
            span.set_attribute("lead_scoring.fit_score", score.fit_score)

            hitl_fields: dict[str, Any] = {
                "hitl_id": None,
                "hitl_state": None,
                "hitl_decided_by": None,
                "hitl_decided_at": None,
                "executed": False,
                "execution_detail": None,
            }

            # High-priority scores gate on HITL; medium/low execute silently.
            if self._hitl is not None and score.priority == "high":
                handle = await self._hitl.request(
                    signal_id=task.signal.id,
                    draft=_score_to_draft(task, score),
                    user_context=(
                        enrichment.lead_context.model_dump()
                        if enrichment.lead_context else None
                    ),
                )
                resolution = await self._hitl.wait(handle.hitl_id)
                hitl_fields.update(
                    hitl_id=resolution.hitl_id,
                    hitl_state=resolution.state,
                    hitl_decided_by=resolution.decided_by,
                    hitl_decided_at=resolution.decided_at,
                )
                if resolution.approved:
                    exec_result = await self._alert_sdr(task, score)
                    hitl_fields["executed"] = bool(exec_result.get("ok"))
                    hitl_fields["execution_detail"] = exec_result
                    await self._hitl.mark_executed(
                        resolution.hitl_id,
                        by="lead_scoring",
                        reason="SDR alert sent",
                    )
            elif score.priority != "low":
                # Medium priority: fire-and-log, no human gate.
                exec_result = await self._alert_sdr(task, score)
                hitl_fields["executed"] = bool(exec_result.get("ok"))
                hitl_fields["execution_detail"] = exec_result

            latency_ms = int((time.perf_counter() - start) * 1000)
            _log.info(
                "lead_scoring.scored",
                signal_id=task.signal.id,
                priority=score.priority,
                fit_score=score.fit_score,
                playbook=score.playbook_slug,
                partial=enrichment.partial,
                executed=hitl_fields["executed"],
                latency_ms=latency_ms,
            )
            return LeadScoringOutput(
                signal_id=task.signal.id,
                enrichment=enrichment,
                score=score.model_dump(),
                latency_ms=latency_ms,
                **hitl_fields,
            )

    # ---------- fan-out ----------

    async def _enrich(self, task: LeadScoringTask) -> Enrichment:
        with _tracer.start_as_current_span("lead_scoring.enrich"):
            lead_task = asyncio.create_task(self._fetch_lead_context(task))
            playbooks_task = asyncio.create_task(self._fetch_playbooks(task))
            lead_ctx, playbooks = await asyncio.gather(
                lead_task, playbooks_task, return_exceptions=True
            )

            errors: dict[str, str] = {}
            ctx: LeadContext | None = None
            if isinstance(lead_ctx, Exception):
                errors["bigquery"] = str(lead_ctx)
            else:
                ctx = lead_ctx

            pbs: list[PlaybookHit] = []
            if isinstance(playbooks, Exception):
                errors["rag"] = str(playbooks)
            else:
                pbs = playbooks

            return Enrichment(
                lead_context=ctx,
                playbooks=pbs,
                partial=bool(errors),
                errors=errors,
            )

    async def _fetch_lead_context(self, task: LeadScoringTask) -> LeadContext | None:
        if not task.signal.user_id:
            return None
        uid = task.signal.user_id
        with _tracer.start_as_current_span("lead_scoring.bq.lead_context"):
            user_sql = (
                f"SELECT * FROM `{self._bq_dataset}.users` WHERE user_id = '{uid}' LIMIT 1"
            )
            usage_sql = (
                f"SELECT event_type, occurred_at FROM `{self._bq_dataset}.usage_events` "
                f"WHERE user_id = '{uid}' ORDER BY occurred_at DESC LIMIT 20"
            )
            user_rows = (await self._mcp.call_tool(
                server="bigquery", tool="query",
                arguments={"sql": user_sql, "max_rows": 1},
            )).get("rows", [])
            usage_rows = (await self._mcp.call_tool(
                server="bigquery", tool="query",
                arguments={"sql": usage_sql, "max_rows": 20},
            )).get("rows", [])

            if not user_rows:
                return LeadContext(lead_id=uid)
            row = user_rows[0]
            # Intent score + CRM stage come from payload when the event source
            # already decorated them (the demo signals do — real pipelines can
            # pre-join upstream).
            payload = task.signal.payload or {}
            return LeadContext(
                lead_id=uid,
                email_domain=(row.get("email") or "").split("@")[-1] or None,
                company=row.get("company"),
                title=row.get("title"),
                seniority=row.get("seniority"),
                plan=row.get("plan"),
                lifecycle_stage=row.get("lifecycle_stage"),
                recent_event_types=[r["event_type"] for r in usage_rows if "event_type" in r],
                crm_stage=payload.get("crm_stage"),
                do_not_contact=bool(payload.get("do_not_contact", False)),
                intent_score=_as_float(payload.get("intent_score") or payload.get("score")),
                raw_rows=user_rows,
            )

    async def _fetch_playbooks(self, task: LeadScoringTask) -> list[PlaybookHit]:
        with _tracer.start_as_current_span("lead_scoring.rag.retrieve"):
            query = (
                f"Signal type: {task.signal.type}. "
                f"Lead id: {task.signal.user_id or 'unknown'}. "
                f"Rationale: {task.decision.rationale}."
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

    async def _alert_sdr(self, task: LeadScoringTask, score: LeadScore) -> dict[str, Any]:
        with _tracer.start_as_current_span("lead_scoring.cio.alert"):
            return await self._mcp.call_tool(
                server="customer-io",
                tool="trigger_broadcast",
                arguments={
                    "signal_id": task.signal.id,
                    "user_id": task.signal.user_id or "unknown",
                    "broadcast_name": self._sdr_broadcast,
                    "data": {
                        "fit_score": score.fit_score,
                        "priority": score.priority,
                        "top_drivers": score.top_drivers,
                        "recommended_action": score.recommended_action,
                        "playbook_slug": score.playbook_slug,
                    },
                },
            )


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _score_to_draft(task: LeadScoringTask, score: LeadScore) -> dict[str, Any]:
    """Shape the score as a HITL draft so the Slack Block Kit UI can render it."""
    return {
        "signal_id": task.signal.id,
        "user_id": task.signal.user_id or "unknown",
        "audience_segment": f"lead_scoring_{score.priority}",
        "channel": "sdr_slack_alert",
        "subject": f"[{score.priority.upper()}] Lead score {score.fit_score} — {task.signal.user_id}",
        "body_markdown": (
            f"**Fit score:** {score.fit_score}/100   **Priority:** {score.priority}\n\n"
            f"**Top drivers:**\n" + "\n".join(f"- {d}" for d in score.top_drivers) + "\n\n"
            f"**Recommended action:** {score.recommended_action}\n\n"
            f"_Rationale: {score.rationale}_"
        ),
        "call_to_action": score.recommended_action,
        "rationale": score.rationale,
        "playbook_slug": score.playbook_slug,
    }
