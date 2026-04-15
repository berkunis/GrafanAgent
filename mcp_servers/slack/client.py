"""Thin async HTTP client for the TypeScript Slack Bolt approval app.

The Bolt app owns the state machine + Block Kit rendering; this client just
talks to its HTTP API so Python agents can drive approvals through MCP.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


class SlackApproverError(RuntimeError):
    pass


class SlackApproverClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 10.0):
        self._base = (base_url or os.getenv("SLACK_APPROVER_URL", "http://localhost:3030")).rstrip("/")
        self._timeout = timeout

    async def request_approval(
        self,
        *,
        signal_id: str,
        channel_id: str,
        draft: dict[str, Any],
        user_context: dict[str, Any] | None = None,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "signal_id": signal_id,
            "channel_id": channel_id,
            "draft": draft,
        }
        if user_context is not None:
            body["user_context"] = user_context
        if timeout_s is not None:
            body["timeout_s"] = timeout_s
        return await self._post("/approvals", body)

    async def get_status(self, hitl_id: str) -> dict[str, Any]:
        return await self._get(f"/approvals/{hitl_id}")

    async def wait_for_approval(self, hitl_id: str, *, timeout_ms: int = 300_000) -> dict[str, Any]:
        return await self._get(
            f"/approvals/{hitl_id}/wait",
            params={"timeout_ms": timeout_ms},
            allow_status=(408,),  # server returned 408 means timed-out wait, not fatal
        )

    async def cancel(self, hitl_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self._post(f"/approvals/{hitl_id}/cancel", {"reason": reason or ""})

    async def mark_executed(self, hitl_id: str, *, by: str = "agent", reason: str = "") -> dict[str, Any]:
        return await self._post(
            f"/approvals/{hitl_id}/executed",
            {"by": by, "reason": reason},
        )

    # ---------- internal ----------

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(self._base + path, json=body)
            return _parse(r, path)

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        allow_status: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout + 300) as c:
            r = await c.get(self._base + path, params=params)
            if r.status_code in allow_status:
                try:
                    return r.json()
                except Exception:
                    return {"error": r.text, "status_code": r.status_code}
            return _parse(r, path)


def _parse(r: httpx.Response, path: str) -> dict[str, Any]:
    if r.status_code >= 400:
        raise SlackApproverError(f"{path} returned {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except Exception as exc:  # noqa: BLE001
        raise SlackApproverError(f"{path} returned non-JSON body") from exc
