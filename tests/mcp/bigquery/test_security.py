import re

import pytest

from mcp_servers.bigquery.security import (
    SecurityError,
    SecurityPolicy,
    cap_rows,
    redact_rows,
    validate_query,
)


POLICY = SecurityPolicy(
    allowed_datasets=("grafanagent_demo",),
    pii_pattern=re.compile(r"^(email|phone|full_name)$", re.IGNORECASE),
    max_rows=100,
)


def test_select_with_qualified_table_passes():
    validate_query("SELECT user_id FROM grafanagent_demo.users", POLICY)


def test_select_with_join_passes():
    validate_query(
        "SELECT u.user_id FROM grafanagent_demo.users u "
        "JOIN grafanagent_demo.usage_events e USING (user_id)",
        POLICY,
    )


def test_unqualified_table_rejected():
    with pytest.raises(SecurityError, match="fully qualified"):
        validate_query("SELECT * FROM users", POLICY)


def test_disallowed_dataset_rejected():
    with pytest.raises(SecurityError, match="allow-list"):
        validate_query("SELECT * FROM prod_secret.pii_dump", POLICY)


def test_insert_rejected():
    with pytest.raises(SecurityError):
        validate_query(
            "INSERT INTO grafanagent_demo.signals (id) VALUES ('x')", POLICY
        )


def test_update_rejected():
    with pytest.raises(SecurityError):
        validate_query(
            "UPDATE grafanagent_demo.users SET plan = 'free' WHERE user_id = 'x'",
            POLICY,
        )


def test_delete_rejected():
    with pytest.raises(SecurityError):
        validate_query("DELETE FROM grafanagent_demo.users WHERE user_id = 'x'", POLICY)


def test_drop_rejected():
    with pytest.raises(SecurityError):
        validate_query("DROP TABLE grafanagent_demo.users", POLICY)


def test_multiple_statements_rejected():
    with pytest.raises(SecurityError, match="exactly one"):
        validate_query(
            "SELECT 1 FROM grafanagent_demo.users; SELECT 2 FROM grafanagent_demo.users",
            POLICY,
        )


def test_empty_query_rejected():
    with pytest.raises(SecurityError, match="empty"):
        validate_query("   ", POLICY)


def test_garbage_rejected():
    with pytest.raises(SecurityError):
        validate_query("not sql at all !!!", POLICY)


def test_redact_rows_scrubs_pii_columns():
    rows = [
        {"user_id": "u1", "email": "a@b.com", "full_name": "Real Person", "plan": "free"},
        {"user_id": "u2", "email": "c@d.com", "full_name": "Other Person", "plan": "team"},
    ]
    cleaned, redacted = redact_rows(rows, POLICY)
    assert redacted == ["email", "full_name"]
    assert all(r["email"] == "[REDACTED]" for r in cleaned)
    assert all(r["full_name"] == "[REDACTED]" for r in cleaned)
    # Non-PII columns preserved.
    assert cleaned[0]["user_id"] == "u1"
    assert cleaned[0]["plan"] == "free"


def test_redact_rows_with_no_pii_is_noop():
    rows = [{"user_id": "u1", "plan": "free"}]
    cleaned, redacted = redact_rows(rows, POLICY)
    assert redacted == []
    assert cleaned == rows


def test_cap_rows_respects_min_of_policy_and_requested():
    rows = [{"i": i} for i in range(200)]
    assert len(cap_rows(rows, POLICY, requested=50)) == 50
    assert len(cap_rows(rows, POLICY, requested=500)) == 100  # capped at policy.max_rows
    assert len(cap_rows(rows, POLICY, requested=0)) == 1       # never zero
