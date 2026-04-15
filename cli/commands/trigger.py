"""`grafanagent trigger` — POST a signal JSON to the router."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.syntax import Syntax

from cli._http import post_json

console = Console()
err = Console(stderr=True)


def trigger(
    signal_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to a JSON file with the Signal payload."
    ),
    url: str = typer.Option(
        "http://localhost:8000/signal",
        "--url",
        "-u",
        help="Router endpoint. Use the Cloud Run URL to hit a deployed router.",
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="HTTP timeout in seconds."
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Print the raw response without syntax highlighting."
    ),
) -> None:
    """Fire a signal at the router and print the RouterResponse."""
    try:
        payload = json.loads(signal_file.read_text())
    except json.JSONDecodeError as exc:
        err.print(f"[red]bad JSON in {signal_file}: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    try:
        resp = post_json(url, payload, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        err.print(f"[red]POST {url} failed: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    if resp.status_code >= 400:
        err.print(f"[red]HTTP {resp.status_code}[/red]")
        err.print(resp.text)
        raise typer.Exit(code=resp.status_code)

    body = resp.json()
    text = json.dumps(body, indent=2)
    if raw:
        console.print(text)
    else:
        console.print(Syntax(text, "json", theme="ansi_dark", word_wrap=True))
