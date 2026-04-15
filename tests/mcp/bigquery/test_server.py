"""Tests for the BigQuery MCP server.

We mock `get_bq_client` to avoid needing real BQ credentials; the tool functions
themselves are exercised by calling the FastMCP tool registrations directly.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from mcp_servers.bigquery import server as bq_server_mod
from mcp_servers.bigquery.security import SecurityPolicy

POLICY = SecurityPolicy(
    allowed_datasets=("grafanagent_demo",),
    pii_pattern=re.compile(r"^(email|full_name)$", re.IGNORECASE),
    max_rows=100,
)


class _FakeQueryJob:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def result(self):  # noqa: D401
        class _Row:
            def __init__(self, data: dict[str, Any]):
                self._data = data

            def __iter__(self):
                return iter(self._data.items())

            def keys(self):
                return self._data.keys()

            def __getitem__(self, key):
                return self._data[key]

        # google.cloud.bigquery.Row supports dict(row); mimic that.
        class _R(dict):
            pass

        return [_R(r) for r in self._rows]


class _FakeBQClient:
    def __init__(self, rows: list[dict[str, Any]] | None = None, table: Any = None):
        self._rows = rows or []
        self._table = table

    def query(self, sql: str) -> _FakeQueryJob:
        return _FakeQueryJob(self._rows)

    def get_table(self, table_ref: str):
        return self._table


class _FakeField:
    def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", description: str | None = None):
        self.name = name
        self.field_type = field_type
        self.mode = mode
        self.description = description


class _FakeTable:
    def __init__(self, schema, num_rows=3, num_bytes=1024):
        self.schema = schema
        self.num_rows = num_rows
        self.num_bytes = num_bytes


def _tools(mcp) -> dict[str, Any]:
    """FastMCP exposes tools via `_tool_manager._tools` (internal)."""
    return mcp._tool_manager._tools  # noqa: SLF001


def _call(mcp, name: str, **kwargs):
    """Invoke a registered tool synchronously by unwrapping the FastMCP wrapper."""
    tool = _tools(mcp)[name]
    return tool.fn(**kwargs)


def test_query_happy_path_redacts_pii(monkeypatch):
    rows = [
        {"user_id": "u1", "email": "a@b.com", "full_name": "Real Person", "plan": "free"},
    ]
    monkeypatch.setattr(bq_server_mod, "get_bq_client", lambda: _FakeBQClient(rows=rows))
    mcp = bq_server_mod.build_mcp_server(POLICY)

    result = _call(mcp, "query", sql="SELECT * FROM grafanagent_demo.users LIMIT 1", max_rows=10)
    assert result["row_count"] == 1
    assert result["rows"][0]["email"] == "[REDACTED]"
    assert result["rows"][0]["full_name"] == "[REDACTED]"
    assert result["rows"][0]["user_id"] == "u1"
    assert set(result["redacted_columns"]) == {"email", "full_name"}


def test_query_rejects_write(monkeypatch):
    monkeypatch.setattr(bq_server_mod, "get_bq_client", lambda: _FakeBQClient())
    mcp = bq_server_mod.build_mcp_server(POLICY)

    result = _call(
        mcp, "query",
        sql="DELETE FROM grafanagent_demo.users WHERE user_id = 'u1'",
        max_rows=1,
    )
    assert "error" in result
    assert result["row_count"] == 0


def test_query_rejects_disallowed_dataset(monkeypatch):
    monkeypatch.setattr(bq_server_mod, "get_bq_client", lambda: _FakeBQClient())
    mcp = bq_server_mod.build_mcp_server(POLICY)

    result = _call(mcp, "query", sql="SELECT * FROM prod_secret.pii_dump", max_rows=1)
    assert "error" in result
    assert "allow-list" in result["error"]


def test_describe_table(monkeypatch):
    table = _FakeTable(
        schema=[_FakeField("user_id", "STRING", "REQUIRED"), _FakeField("email", "STRING")],
        num_rows=42,
    )
    monkeypatch.setattr(bq_server_mod, "get_bq_client", lambda: _FakeBQClient(table=table))
    mcp = bq_server_mod.build_mcp_server(POLICY)

    result = _call(mcp, "describe_table", table_ref="grafanagent_demo.users")
    assert result["row_count"] == 42
    assert result["schema"][0]["name"] == "user_id"
    assert result["schema"][0]["mode"] == "REQUIRED"


def test_describe_table_rejects_disallowed():
    mcp = bq_server_mod.build_mcp_server(POLICY)
    result = _call(mcp, "describe_table", table_ref="prod_secret.pii")
    assert "error" in result


def test_list_signals_applies_since_filter(monkeypatch):
    observed: list[str] = []

    def _fake_client():
        class C:
            def query(self, sql):
                observed.append(sql)
                return _FakeQueryJob([])
        return C()

    monkeypatch.setattr(bq_server_mod, "get_bq_client", _fake_client)
    monkeypatch.setenv("BQ_DATASET", "grafanagent_demo")

    mcp = bq_server_mod.build_mcp_server(POLICY)
    since = datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat()
    result = _call(mcp, "list_signals", since=since, limit=5)
    assert result["row_count"] == 0
    assert observed, "query was never called"
    assert "signals" in observed[0]
    assert since in observed[0]
