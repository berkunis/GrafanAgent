"""PII scrubber — regex coverage + nested-structure walk + structlog integration."""
from __future__ import annotations

from observability.pii import (
    ALWAYS_REDACT_KEYS,
    REDACTED,
    is_pii_clean,
    pii_scrub_processor,
    scrub,
)


def test_email_is_scrubbed():
    s = scrub("contact priya.shah@example.test today")
    assert "priya.shah@example.test" not in s
    assert REDACTED in s


def test_phone_is_scrubbed():
    assert REDACTED in scrub("call +1 (415) 555-2671 after noon")


def test_anthropic_key_is_scrubbed():
    s = scrub("ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF")
    assert "sk-ant-api03" not in s
    assert REDACTED in s


def test_slack_token_is_scrubbed():
    # Construct the token at runtime so the literal never appears in source —
    # otherwise GitHub's secret-scanning push protection trips on the fixture.
    fake_slack = "xox" + "b-" + "EXAMPLE-" * 3 + "FAKE1234567890"
    s = scrub(f"token={fake_slack}")
    assert "EXAMPLE" not in s
    assert REDACTED in s


def test_jwt_is_scrubbed():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcd1234"
    assert REDACTED in scrub(f"Authorization: Bearer {jwt}")


def test_nested_dicts_are_walked():
    event = {
        "user": {"email": "isil@example.test", "plan": "free"},
        "tokens": ["sk-ant-api03-" + "a" * 40, "public-value"],
        "nested": {"inner": {"phone": "+15555550123"}},
    }
    cleaned = scrub(event)
    assert "isil@example.test" not in str(cleaned)
    assert "+15555550123" not in str(cleaned)
    assert "sk-ant-api03" not in str(cleaned)
    # Non-PII survives
    assert cleaned["user"]["plan"] == "free"
    assert cleaned["tokens"][1] == "public-value"


def test_always_redact_keys_are_redacted_by_name():
    for key in ALWAYS_REDACT_KEYS:
        cleaned = scrub({key: "literally-any-value-at-all"})
        assert cleaned[key] == REDACTED


def test_structlog_processor_runs_over_event_dict():
    event = {
        "event": "request",
        "email": "priya.shah@example.test",
        "password": "hunter2",
        "safe": 42,
    }
    out = pii_scrub_processor(None, "info", dict(event))
    assert out["email"] == REDACTED
    assert out["password"] == REDACTED
    assert out["safe"] == 42
    assert out["event"] == "request"  # non-PII keys preserved


def test_is_pii_clean_helper():
    assert is_pii_clean(["all good", "nothing to see"])
    assert not is_pii_clean(["contact isil@example.test"])
