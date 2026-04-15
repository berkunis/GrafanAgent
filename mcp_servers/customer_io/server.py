"""Customer.io MCP server — sandbox-only, idempotent writes.

Tools:
  - create_campaign_draft(signal_id, user_id, audience_segment, channel,
    subject, body_markdown, call_to_action, playbook_slug?, rationale)
      Pure shaping; no network call. The lifecycle agent invokes this to
      produce a HITL-reviewable `CampaignDraft`.

  - trigger_broadcast(signal_id, user_id, broadcast_name, data?)
      Fires a Customer.io tracked event that can trigger a campaign. Guarded
      by the sandbox check and idempotent on `signal_id`.

  - add_to_segment(signal_id, segment_id, customer_ids)
      Adds customers to a manual segment. Idempotent on `signal_id`.

  - get_campaign_membership(user_id)
      Returns current campaign memberships. Requires an App-API key (not
      provided in this demo); returns `{campaigns: [], note: "..."}` so the
      agent can see an empty state without crashing.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

from mcp_servers.customer_io.client import CIOClient, CIOError, build_default_client, require_sandbox
from mcp_servers.customer_io.idempotency import IdempotencyCache, derive_key
from mcp_servers.customer_io.schemas import CampaignDraft, WriteResult
from observability import get_logger

_tracer = trace.get_tracer("mcp.customer_io")
_log = get_logger("mcp.customer_io")


def build_mcp_server(
    *,
    client: CIOClient | None = None,
    cache: IdempotencyCache | None = None,
) -> FastMCP:
    ic = cache or IdempotencyCache()
    # Resolve the client lazily so SMOKE=1 boot does not require env vars.
    _client_ref: dict[str, CIOClient] = {}

    def _cio() -> CIOClient:
        if client is not None:
            return client
        if "c" not in _client_ref:
            _client_ref["c"] = build_default_client()
        return _client_ref["c"]

    mcp = FastMCP("grafanagent-customer-io")

    @mcp.tool(
        name="create_campaign_draft",
        description=(
            "Produce a structured Customer.io campaign draft from the lifecycle agent. "
            "This tool does NOT send anything — it returns a draft the HITL Slack gate will review."
        ),
    )
    def create_campaign_draft(
        signal_id: str,
        user_id: str,
        audience_segment: str,
        channel: str,
        subject: str,
        body_markdown: str,
        call_to_action: str,
        rationale: str,
        playbook_slug: str | None = None,
    ) -> dict[str, Any]:
        with _tracer.start_as_current_span("cio.create_campaign_draft") as span:
            span.set_attribute("grafanagent.signal_id", signal_id)
            span.set_attribute("grafanagent.channel", channel)
            draft = CampaignDraft(
                signal_id=signal_id,
                user_id=user_id,
                audience_segment=audience_segment,
                channel=channel,
                subject=subject,
                body_markdown=body_markdown,
                call_to_action=call_to_action,
                rationale=rationale,
                playbook_slug=playbook_slug,
            )
            return draft.model_dump()

    @mcp.tool(
        name="trigger_broadcast",
        description=(
            "Trigger a Customer.io broadcast for a single customer by emitting a tracked event. "
            "Idempotent on signal_id; refuses unless CUSTOMERIO_SANDBOX=1."
        ),
    )
    def trigger_broadcast(
        signal_id: str,
        user_id: str,
        broadcast_name: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = derive_key(signal_id, f"broadcast:{broadcast_name}")
        cached = ic.get(key)
        if cached is not None:
            return WriteResult(ok=True, idempotency_key=key, already_seen=True, detail=cached).model_dump()

        with _tracer.start_as_current_span("cio.trigger_broadcast") as span:
            span.set_attribute("grafanagent.signal_id", signal_id)
            span.set_attribute("cio.broadcast_name", broadcast_name)
            try:
                require_sandbox()
                resp = _cio().track(customer_id=user_id, name=broadcast_name, **(data or {}))
            except CIOError as exc:
                _log.warning("cio.trigger_broadcast.refused", reason=str(exc), signal_id=signal_id)
                return WriteResult(ok=False, idempotency_key=key, error=str(exc)).model_dump()
            except Exception as exc:  # noqa: BLE001
                _log.exception("cio.trigger_broadcast.error", signal_id=signal_id)
                return WriteResult(ok=False, idempotency_key=key, error=str(exc)).model_dump()

        detail = {"response": resp if isinstance(resp, dict) else repr(resp)}
        ic.put(key, detail)
        return WriteResult(ok=True, idempotency_key=key, detail=detail).model_dump()

    @mcp.tool(
        name="add_to_segment",
        description=(
            "Add one or more customers to a manual Customer.io segment. "
            "Idempotent on signal_id; refuses unless CUSTOMERIO_SANDBOX=1."
        ),
    )
    def add_to_segment(
        signal_id: str,
        segment_id: int,
        customer_ids: list[str],
    ) -> dict[str, Any]:
        key = derive_key(signal_id, f"segment:{segment_id}")
        cached = ic.get(key)
        if cached is not None:
            return WriteResult(ok=True, idempotency_key=key, already_seen=True, detail=cached).model_dump()

        with _tracer.start_as_current_span("cio.add_to_segment") as span:
            span.set_attribute("grafanagent.signal_id", signal_id)
            span.set_attribute("cio.segment_id", segment_id)
            span.set_attribute("cio.customer_count", len(customer_ids))
            try:
                require_sandbox()
                resp = _cio().add_to_segment(segment_id=segment_id, customer_ids=customer_ids)
            except CIOError as exc:
                _log.warning("cio.add_to_segment.refused", reason=str(exc), signal_id=signal_id)
                return WriteResult(ok=False, idempotency_key=key, error=str(exc)).model_dump()
            except Exception as exc:  # noqa: BLE001
                _log.exception("cio.add_to_segment.error", signal_id=signal_id)
                return WriteResult(ok=False, idempotency_key=key, error=str(exc)).model_dump()

        detail = {"response": resp if isinstance(resp, dict) else repr(resp)}
        ic.put(key, detail)
        return WriteResult(ok=True, idempotency_key=key, detail=detail).model_dump()

    @mcp.tool(
        name="get_campaign_membership",
        description=(
            "Return current campaign memberships for a user. "
            "Requires an App-API key which this demo does not ship with; returns "
            "an empty list plus an explanatory note so agents can proceed without crashing."
        ),
    )
    def get_campaign_membership(user_id: str) -> dict[str, Any]:
        with _tracer.start_as_current_span("cio.get_campaign_membership") as span:
            span.set_attribute("cio.user_id", user_id)
            return {
                "user_id": user_id,
                "campaigns": [],
                "note": (
                    "App-API not configured; in production this tool queries "
                    "https://api.customer.io/v1/customers/{id}/campaigns."
                ),
            }

    return mcp


def create_app(**kwargs: Any) -> FastAPI:
    mcp = build_mcp_server(**kwargs)
    app = FastAPI(title="mcp-customer-io", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "server": "customer_io"}

    app.mount("/mcp", mcp.streamable_http_app())
    return app


def main() -> None:
    from observability import get_logger, get_tracer, init_telemetry

    init_telemetry("mcp.customer_io")
    log = get_logger("mcp.customer_io")
    tracer = get_tracer("mcp.customer_io")

    with tracer.start_as_current_span("mcp.customer_io.boot"):
        log.info(
            "mcp.alive",
            server="customer_io",
            tools=["create_campaign_draft", "trigger_broadcast", "add_to_segment", "get_campaign_membership"],
        )

    if os.getenv("SMOKE") == "1":
        return

    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
