"""Per-signal context propagation.

The router / lifecycle stack runs many LLM + MCP calls per Signal. We want
every metric and span they emit to carry the `grafanagent.signal_id`
attribute so the Grafana dashboard can ask "what did *this* one signal
cost?" — which is the single most useful question in a per-user cost demo.

Implementation: a `contextvars.ContextVar` that's set at the request
boundary (FastAPI middleware, CLI entrypoint, lifecycle orchestrator) and
read wherever a span or metric attribute is assembled. Using contextvars
means it survives `asyncio.create_task` / `gather` fan-out automatically
— exactly what we need for the lifecycle parallel fan-out.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_SIGNAL_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "grafanagent_signal_id", default=None
)
_SIGNAL_TYPE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "grafanagent_signal_type", default=None
)


def current_signal_id() -> str | None:
    return _SIGNAL_ID.get()


def current_signal_type() -> str | None:
    return _SIGNAL_TYPE.get()


def current_attrs() -> dict[str, str]:
    """Attribute bag for span.set_attribute / metric labels. Omits unset keys."""
    out: dict[str, str] = {}
    if (sid := _SIGNAL_ID.get()) is not None:
        out["grafanagent.signal_id"] = sid
    if (stype := _SIGNAL_TYPE.get()) is not None:
        out["grafanagent.signal_type"] = stype
    return out


@contextmanager
def signal_context(signal_id: str, signal_type: str | None = None) -> Iterator[None]:
    """Scope a block of async/sync code to a given signal. Nested calls push
    new values and restore cleanly on exit (contextvars semantics)."""
    id_token = _SIGNAL_ID.set(signal_id)
    type_token = _SIGNAL_TYPE.set(signal_type) if signal_type else None
    try:
        yield
    finally:
        _SIGNAL_ID.reset(id_token)
        if type_token is not None:
            _SIGNAL_TYPE.reset(type_token)
