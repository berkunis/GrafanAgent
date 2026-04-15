"""Shared httpx wrapper for CLI commands that talk to running services.

Kept tiny so tests can inject a `DummyHttp` by setting the module-level
`_sender`. Production uses httpx directly.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

import httpx


class HttpSender(Protocol):
    def post(self, url: str, json: dict[str, Any], timeout: float) -> httpx.Response: ...


class _DefaultSender:
    def post(self, url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        return httpx.post(url, json=json, timeout=timeout)


_sender: HttpSender = _DefaultSender()


def set_sender(new: HttpSender) -> Callable[[], None]:
    """Inject a fake sender; returns a reset callable."""
    global _sender
    old = _sender
    _sender = new

    def _reset() -> None:
        global _sender
        _sender = old

    return _reset


def post_json(url: str, body: dict[str, Any], *, timeout: float = 30.0) -> httpx.Response:
    return _sender.post(url, json=body, timeout=timeout)
