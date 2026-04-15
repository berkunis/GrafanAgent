"""Attribution orchestrator — fan-out + Sonnet analysis.

No HITL gate on this path: attribution reports are read-only/informational,
posted to a RevOps Slack channel without needing per-report approval. The
canonical playbook note: "transparency beats polish on internal reports."

Structure mirrors lifecycle + lead_scoring so the three agents read the
same to a reviewer.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from opentelemetry import trace

from agents._llm import LLMClient
from agents._mcp import McpClient
from agents.attribution.agent import synthesize_report
from agents.attribution.schemas import (
    AttributionOutput,
    AttributionTask,
    ConversionContext,
    Enrichment,
    PlaybookHit,
    TouchpointRow,
)
from observability import get_logger, signal_context
from rag.retriever import Retriever

_tracer = trace.get_tracer("agents.attribution.orchestrator")
_log = get_logger("attribution")

DEFAULT_POST_CHANNEL = os.getenv("ATTRIBUTION_POST_CHANNEL", "")


class AttributionOrchestrator:
    def __init__(
        self,
        *,
        llm: LLMClient,
        mcp: McpClient,
        retriever: Retriever,
        bq_dataset: str = "grafanagent_demo",
        post_channel: str = DEFAULT_POST_CHANNEL,
    ):
        self._llm = llm
        self._mcp = mcp
        self._retriever = retriever
        self._bq_dataset = bq_dataset
        self._post_channel = post_channel

    async def run(self, task: AttributionTask) -> AttributionOutput:
        start = time.perf_counter()
        with (
            signal_context(task.signal.id, task.signal.type),
            _tracer.start_as_current_span("attribution.run") as span,
        ):
            span.set_attribute("grafanagent.signal_id", task.signal.id)
            span.set_attribute("grafanagent.signal_type", task.signal.type)

            enrichment = await self._enrich(task)
            span.set_attribute("attribution.enrichment.partial", enrichment.partial)
            span.set_attribute(
                "attribution.enrichment.playbooks",
                [p.playbook_slug for p in enrichment.playbooks],
            )

            report = await synthesize_report(llm=self._llm, task=task, enrichment=enrichment)
            span.set_attribute("attribution.confidence", report.confidence)

            posted_detail = None
            posted_channel = None
            if self._post_channel:
                posted_channel = self._post_channel
                posted_detail = await self._post(task, report, self._post_channel)

            latency_ms = int((time.perf_counter() - start) * 1000)
            _log.info(
                "attribution.reported",
                signal_id=task.signal.id,
                confidence=report.confidence,
                first_touch=report.first_touch,
                last_touch=report.last_touch,
                playbook=report.playbook_slug,
                partial=enrichment.partial,
                posted_to=posted_channel,
                latency_ms=latency_ms,
            )
            return AttributionOutput(
                signal_id=task.signal.id,
                enrichment=enrichment,
                report=report.model_dump(),
                latency_ms=latency_ms,
                posted_to_channel=posted_channel,
                posted_message_detail=posted_detail,
            )

    # ---------- fan-out ----------

    async def _enrich(self, task: AttributionTask) -> Enrichment:
        with _tracer.start_as_current_span("attribution.enrich"):
            ctx_task = asyncio.create_task(self._fetch_conversion_context(task))
            playbooks_task = asyncio.create_task(self._fetch_playbooks(task))
            ctx, playbooks = await asyncio.gather(
                ctx_task, playbooks_task, return_exceptions=True
            )

            errors: dict[str, str] = {}
            conversion_ctx: ConversionContext | None = None
            if isinstance(ctx, Exception):
                errors["bigquery"] = str(ctx)
            else:
                conversion_ctx = ctx

            pbs: list[PlaybookHit] = []
            if isinstance(playbooks, Exception):
                errors["rag"] = str(playbooks)
            else:
                pbs = playbooks

            return Enrichment(
                conversion_context=conversion_ctx,
                playbooks=pbs,
                partial=bool(errors),
                errors=errors,
            )

    async def _fetch_conversion_context(self, task: AttributionTask) -> ConversionContext:
        uid = task.signal.user_id
        payload = task.signal.payload or {}
        with _tracer.start_as_current_span("attribution.bq.conversion_context"):
            touches_rows: list[dict[str, Any]] = []
            opps: list[dict[str, Any]] = []
            if uid:
                touches_sql = (
                    f"SELECT event_type AS campaign_id, 'app' AS channel, "
                    f"CAST(occurred_at AS STRING) AS touch_at "
                    f"FROM `{self._bq_dataset}.usage_events` "
                    f"WHERE user_id = '{uid}' ORDER BY occurred_at ASC LIMIT 30"
                )
                touches_rows = (await self._mcp.call_tool(
                    server="bigquery", tool="query",
                    arguments={"sql": touches_sql, "max_rows": 30},
                )).get("rows", [])
            touches = [
                TouchpointRow(
                    campaign_id=str(r.get("campaign_id", "unattributed")),
                    channel=str(r.get("channel", "unknown")),
                    touch_at=str(r.get("touch_at", "")),
                    utm_source=r.get("utm_source"),
                )
                for r in touches_rows
            ]
            return ConversionContext(
                user_id=uid,
                plan_transition=payload.get("plan_transition"),
                cohort_size=_as_int(payload.get("cohort_size")),
                touches=touches,
                opportunities=opps,
            )

    async def _fetch_playbooks(self, task: AttributionTask) -> list[PlaybookHit]:
        with _tracer.start_as_current_span("attribution.rag.retrieve"):
            query = (
                f"Signal type: {task.signal.type}. "
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

    async def _post(
        self, task: AttributionTask, report: Any, channel_id: str
    ) -> dict[str, Any]:
        with _tracer.start_as_current_span("attribution.slack.post"):
            blocks_md = _format_report_md(report)
            # Use the Slack MCP request_approval tool (no-gate): we reuse it as a
            # plain post because it's the only slack-facing tool in our mesh.
            # The HITL state proceeds straight to "posted" and stays there —
            # the attribution path never consults wait_for_approval.
            return await self._mcp.call_tool(
                server="slack",
                tool="request_approval",
                arguments={
                    "signal_id": task.signal.id,
                    "channel_id": channel_id,
                    "draft": {
                        "signal_id": task.signal.id,
                        "user_id": task.signal.user_id or "revops",
                        "audience_segment": "revops_report",
                        "channel": "slack",
                        "subject": f"Attribution report — {task.signal.type}",
                        "body_markdown": blocks_md,
                        "call_to_action": "Review report",
                        "rationale": report.top_driver_rationale,
                        "playbook_slug": report.playbook_slug,
                    },
                },
            )


def _as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _format_report_md(report: Any) -> str:
    multi = "\n".join(
        f"- `{m.campaign_id}` ({m.channel}) — {m.weight:.0%}" for m in report.multi_touch
    )
    return (
        f"**Confidence:** {report.confidence}\n"
        f"**First touch:** `{report.first_touch}`\n"
        f"**Last touch:** `{report.last_touch}`\n\n"
        f"**Multi-touch attribution:**\n{multi}\n\n"
        f"**Top driver:** {report.top_driver_rationale}\n\n"
        f"**Verdict:**\n{report.three_line_verdict}\n"
    )
