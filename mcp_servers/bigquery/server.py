"""BigQuery MCP server — read-only, allow-list-gated, PII-redacting.

Three tools:

- `query(sql, max_rows)`        — execute a validated SELECT and return rows.
- `describe_table(table_ref)`   — return schema + row count for `dataset.table`.
- `list_signals(since, limit)`  — convenience: rows from `<dataset>.signals`
  newer than the given ISO timestamp. Used by the demo + tests.

The server is exposed over MCP streamable-HTTP and mounted at `/mcp` inside a
FastAPI app so we can also surface `/healthz` for Cloud Run probes.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from google.cloud import bigquery
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

from mcp_servers.bigquery.security import (
    SecurityError,
    SecurityPolicy,
    cap_rows,
    redact_rows,
    validate_query,
)
from observability import get_logger

_tracer = trace.get_tracer("mcp.bigquery")
_log = get_logger("mcp.bigquery")

# Singleton BQ client — instantiated lazily so SMOKE=1 boot does not require ADC.
_bq_client: bigquery.Client | None = None


def get_bq_client() -> bigquery.Client:
    """Lazy singleton; tests monkeypatch this to inject a fake."""
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client()
    return _bq_client


def _row_to_dict(row: bigquery.Row) -> dict[str, Any]:
    return {k: _coerce(v) for k, v in dict(row).items()}


def _coerce(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_mcp_server(policy: SecurityPolicy | None = None) -> FastMCP:
    """Construct the FastMCP server with all tools registered."""
    pol = policy or SecurityPolicy.from_env()
    mcp = FastMCP("grafanagent-bigquery")

    @mcp.tool(
        name="query",
        description=(
            "Execute a read-only SELECT query against an allow-listed BigQuery dataset. "
            "PII columns are redacted from results. "
            f"Allowed datasets: {', '.join(pol.allowed_datasets)}."
        ),
    )
    def query(sql: str, max_rows: int = 100) -> dict[str, Any]:
        with _tracer.start_as_current_span("bigquery.query") as span:
            span.set_attribute("db.system", "bigquery")
            span.set_attribute("db.statement", sql[:1000])
            span.set_attribute("grafanagent.max_rows_requested", max_rows)
            try:
                validate_query(sql, pol)
            except SecurityError as exc:
                span.record_exception(exc)
                _log.warning("bigquery.query.rejected", reason=str(exc))
                return {"error": str(exc), "rows": [], "row_count": 0}

            client = get_bq_client()
            job = client.query(sql)
            raw_rows = [_row_to_dict(r) for r in job.result()]
            capped = cap_rows(raw_rows, pol, max_rows)
            cleaned, redacted_cols = redact_rows(capped, pol)

            span.set_attribute("grafanagent.row_count", len(cleaned))
            span.set_attribute("grafanagent.redacted_columns", redacted_cols)
            _log.info(
                "bigquery.query.ok",
                row_count=len(cleaned),
                redacted_columns=redacted_cols,
                truncated=len(raw_rows) > len(capped),
            )
            return {
                "rows": cleaned,
                "row_count": len(cleaned),
                "truncated": len(raw_rows) > len(capped),
                "redacted_columns": redacted_cols,
            }

    @mcp.tool(
        name="describe_table",
        description=(
            "Return the schema and row count of a fully-qualified BigQuery table "
            "(`dataset.table`). Useful for the agent to discover columns before querying."
        ),
    )
    def describe_table(table_ref: str) -> dict[str, Any]:
        with _tracer.start_as_current_span("bigquery.describe_table") as span:
            span.set_attribute("db.system", "bigquery")
            span.set_attribute("grafanagent.table_ref", table_ref)
            if "." not in table_ref:
                return {"error": "table_ref must be 'dataset.table' or 'project.dataset.table'"}
            dataset_id = table_ref.rsplit(".", 1)[0].split(".")[-1]
            if dataset_id not in pol.allowed_datasets:
                return {"error": f"dataset '{dataset_id}' not in allow-list"}

            client = get_bq_client()
            table = client.get_table(table_ref)
            schema = [
                {"name": f.name, "type": f.field_type, "mode": f.mode, "description": f.description}
                for f in table.schema
            ]
            span.set_attribute("grafanagent.row_count", table.num_rows or 0)
            return {
                "table_ref": table_ref,
                "row_count": table.num_rows,
                "size_bytes": table.num_bytes,
                "schema": schema,
            }

    @mcp.tool(
        name="list_signals",
        description=(
            "Convenience: return rows from the `signals` table newer than the given "
            "ISO-8601 timestamp. The dataset is taken from the BQ_DATASET env var."
        ),
    )
    def list_signals(since: str | None = None, limit: int = 50) -> dict[str, Any]:
        dataset = os.getenv("BQ_DATASET", pol.allowed_datasets[0])
        clauses = ["TRUE"]
        if since:
            clauses.append(f"occurred_at >= TIMESTAMP('{since}')")
        sql = (
            f"SELECT * FROM `{dataset}.signals` "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY occurred_at DESC LIMIT {min(limit, pol.max_rows)}"
        )
        return query(sql, max_rows=limit)

    return mcp


def create_app(policy: SecurityPolicy | None = None) -> FastAPI:
    """ASGI app with `/healthz` and the MCP transport mounted at `/mcp`."""
    mcp = build_mcp_server(policy)
    app = FastAPI(title="mcp-bigquery", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "server": "bigquery"}

    app.mount("/mcp", mcp.streamable_http_app())
    return app


def main() -> None:
    """Entrypoint. SMOKE=1 boots and exits; otherwise serves on $PORT."""
    from observability import get_logger, get_tracer, init_telemetry

    init_telemetry("mcp.bigquery")
    log = get_logger("mcp.bigquery")
    tracer = get_tracer("mcp.bigquery")

    with tracer.start_as_current_span("mcp.bigquery.boot"):
        log.info("mcp.alive", server="bigquery", tools=["query", "describe_table", "list_signals"])

    if os.getenv("SMOKE") == "1":
        return

    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
