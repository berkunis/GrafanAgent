"""Security layer for the BigQuery MCP server.

Three guards run on every `query` call:

1. **Read-only SQL check** — parse with sqlglot; reject anything that is not
   a SELECT (DDL, DML, MERGE, CALL, etc. all blocked).
2. **Dataset allow-list** — every referenced table must live in a dataset
   the operator explicitly allowed via `BQ_ALLOWED_DATASETS`.
3. **PII column redaction** — any returned column whose name matches the
   configured PII pattern is replaced with `"[REDACTED]"` before the result
   leaves this process. Names are pattern-matched, not value-matched, so this
   is best-effort and supplements (does not replace) source-system PII handling.

`SecurityError` is raised when a guard rejects a request. The MCP server
translates it into an MCP error so the agent gets a clear failure mode.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import expressions as exp

DEFAULT_ALLOWED_DATASETS = ("grafanagent_demo",)
DEFAULT_PII_PATTERN = (
    r"^(email|email_address|phone|phone_number|ssn|full_name|first_name|"
    r"last_name|address|street|ip_address|password|api_key|access_token)$"
)
DEFAULT_MAX_ROWS = 1000


class SecurityError(ValueError):
    """Raised when a query violates allow-list, read-only, or row-cap rules."""


@dataclass(frozen=True)
class SecurityPolicy:
    allowed_datasets: tuple[str, ...]
    pii_pattern: re.Pattern[str]
    max_rows: int

    @classmethod
    def from_env(cls) -> "SecurityPolicy":
        ds_raw = os.getenv("BQ_ALLOWED_DATASETS")
        datasets = (
            tuple(d.strip() for d in ds_raw.split(",") if d.strip())
            if ds_raw
            else DEFAULT_ALLOWED_DATASETS
        )
        return cls(
            allowed_datasets=datasets,
            pii_pattern=re.compile(
                os.getenv("BQ_PII_COLUMNS_REGEX", DEFAULT_PII_PATTERN), re.IGNORECASE
            ),
            max_rows=int(os.getenv("BQ_MAX_ROWS", str(DEFAULT_MAX_ROWS))),
        )


def validate_query(sql: str, policy: SecurityPolicy) -> None:
    """Parse and validate a SQL string. Raises `SecurityError` on violation."""
    if not sql or not sql.strip():
        raise SecurityError("query is empty")

    try:
        statements = sqlglot.parse(sql, dialect="bigquery")
    except sqlglot.errors.ParseError as exc:
        raise SecurityError(f"could not parse SQL: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SecurityError(
            f"exactly one statement allowed; got {len(statements)}"
        )

    stmt = statements[0]
    if not isinstance(stmt, (exp.Select, exp.Subquery, exp.Union, exp.With)):
        raise SecurityError(
            f"only SELECT statements are permitted; got {stmt.key.upper()}"
        )

    # Reject any DDL/DML hiding inside the statement (e.g., CTEs that mutate).
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create,
        exp.Drop, exp.Alter, exp.AlterColumn, exp.TruncateTable,
        exp.Command,
    )
    for node in stmt.walk():
        # `walk()` yields nodes (not tuples) on modern sqlglot versions; older versions
        # yielded (node, parent, key). Handle both.
        candidate = node[0] if isinstance(node, tuple) else node
        if isinstance(candidate, forbidden):
            raise SecurityError(
                f"forbidden statement type embedded in query: {candidate.key.upper()}"
            )

    # Validate every referenced table sits in an allowed dataset.
    for table in stmt.find_all(exp.Table):
        dataset = table.db
        if not dataset:
            raise SecurityError(
                f"table '{table.name}' must be fully qualified as `dataset.table`"
            )
        if dataset not in policy.allowed_datasets:
            raise SecurityError(
                f"dataset '{dataset}' is not in the allow-list "
                f"({', '.join(policy.allowed_datasets)})"
            )


def redact_rows(
    rows: list[dict[str, Any]],
    policy: SecurityPolicy,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Replace PII-column values with `[REDACTED]`. Returns (new_rows, redacted_columns)."""
    if not rows:
        return rows, []
    redacted_cols = sorted({col for col in rows[0].keys() if policy.pii_pattern.match(col)})
    if not redacted_cols:
        return rows, []
    cleaned = [
        {col: ("[REDACTED]" if col in redacted_cols else val) for col, val in row.items()}
        for row in rows
    ]
    return cleaned, redacted_cols


def cap_rows(rows: list[dict[str, Any]], policy: SecurityPolicy, requested: int) -> list[dict[str, Any]]:
    """Apply both the policy cap and the per-call requested cap."""
    cap = min(policy.max_rows, max(1, requested))
    return rows[:cap]
