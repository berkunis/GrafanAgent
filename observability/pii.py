"""PII scrubber for structured logs.

`pii_scrub_processor` is a structlog processor that walks the event dict and
replaces values matching PII patterns with `[REDACTED]`. Drops into the
structlog pipeline before the renderer so nothing PII hits Loki or stdout.

Scope (pragmatic, not exhaustive):
    - email addresses
    - phone numbers (E.164 and common NANP shapes)
    - credit card numbers (13–19 digits, grouped or not)
    - API tokens (Anthropic sk-ant-*, OpenAI sk-proj-*, Slack xox*-*, JWTs)
    - long opaque hex/secret-ish strings (≥ 32 chars of [A-Za-z0-9_-])

Scrubs recursively through dicts, lists, and tuples. Strings are pattern-
matched; numbers/bools are left alone. Keys listed in `ALWAYS_REDACT_KEYS`
are redacted by-name regardless of value shape.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

ALWAYS_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "secret",
        "credit_card",
        "card_number",
        "ssn",
    }
)

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Domain-specific tokens first so the generic phone / opaque patterns
    # can never eat a substring of a real secret.
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    # Phone — require either a leading `+` or at least one non-digit separator
    # in the middle so a plain 10-digit numeric string inside a token doesn't
    # get chomped.
    ("phone", re.compile(r"\+\d[\d \-().]{7,}\d|\d{3}[ \-.]\d{3}[ \-.]\d{4}")),
    # Long opaque secret-looking strings. Runs last.
    ("opaque_secret", re.compile(r"\b[A-Za-z0-9_-]{32,}\b")),
)


def scrub(value: Any) -> Any:
    """Recursively scrub PII out of any value. Safe for nested dicts/lists."""
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in ALWAYS_REDACT_KEYS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub(v) for v in value)
    return value


def _scrub_string(text: str) -> str:
    out = text
    for _, pat in _PATTERNS:
        out = pat.sub(REDACTED, out)
    return out


def pii_scrub_processor(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor. Scrubs the entire event dict in place."""
    return {
        key: (REDACTED if key.lower() in ALWAYS_REDACT_KEYS else scrub(val))
        for key, val in event_dict.items()
    }


def is_pii_clean(strings: Iterable[str]) -> bool:
    """Utility for tests: True if none of the strings contain a known PII shape."""
    for s in strings:
        for _, pat in _PATTERNS:
            if pat.search(s):
                return False
    return True
