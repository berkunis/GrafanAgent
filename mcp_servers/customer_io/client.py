"""Customer.io client wrapper — thin, injectable, sandbox-guarded.

We intentionally avoid leaning on the full Customer.io surface. For the
lifecycle demo we only need:
  - track an event (used under the hood for broadcast triggers)
  - add a customer to a segment
The real SDK call is wrapped so tests can inject a fake.
"""
from __future__ import annotations

import os
from typing import Any, Protocol


class CIOError(RuntimeError):
    """Raised when a Customer.io call fails or the sandbox guard trips."""


class CIOClient(Protocol):
    def track(self, customer_id: str, name: str, **data: Any) -> Any: ...
    def add_to_segment(self, segment_id: int, customer_ids: list[str]) -> Any: ...


def require_sandbox() -> None:
    """Refuse to do anything if we aren't explicitly in sandbox mode.

    Two env vars together act as a belt-and-braces: `CUSTOMERIO_SANDBOX=1` is
    required, and `CUSTOMERIO_ENV` must not be `prod`. Missing either trips.
    """
    sandbox = os.getenv("CUSTOMERIO_SANDBOX", "").strip()
    env = os.getenv("CUSTOMERIO_ENV", "sandbox").strip().lower()
    if sandbox != "1" or env == "prod":
        raise CIOError(
            "Customer.io writes are disabled unless CUSTOMERIO_SANDBOX=1 and "
            "CUSTOMERIO_ENV != 'prod'. This is a hard guard — refusing."
        )


def build_default_client() -> CIOClient:
    """Construct a real `customerio.CustomerIO` from env. Used by the server
    at boot; tests inject their own fake via `build_mcp_server(client=...)`."""
    from customerio import CustomerIO, Regions

    site = os.environ["CUSTOMERIO_SITE_ID"]
    key = os.environ["CUSTOMERIO_API_KEY"]
    region_env = os.getenv("CUSTOMERIO_REGION", "us").lower()
    region = Regions.EU if region_env == "eu" else Regions.US
    return CustomerIO(site_id=site, api_key=key, region=region)
