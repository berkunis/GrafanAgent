"""`grafanagent replay` — re-run a signal captured earlier.

Phase 4 reads from a local JSON file; Phase 6 will add `--from-trace <id>` to
fetch the original signal payload from Tempo and re-execute.
"""
from __future__ import annotations

from pathlib import Path

import typer

from cli.commands.trigger import trigger


def replay(
    signal_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to a JSON file with the captured Signal payload."
    ),
    url: str = typer.Option(
        "http://localhost:8000/signal", "--url", "-u", help="Router endpoint."
    ),
    timeout: float = typer.Option(30.0, "--timeout", "-t"),
) -> None:
    """Re-send a stored signal. Useful for prompt-regression comparison."""
    # Replay is a POST of the same payload — delegate to `trigger` so the
    # output shape is identical and any future HTTP plumbing lands in one place.
    trigger(signal_file=signal_file, url=url, timeout=timeout, raw=False)
