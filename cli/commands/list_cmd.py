"""`grafanagent list [agents|signals|playbooks]` — quick inventory of the system."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agents.router.rules import RULE_TABLE
from cli._registry import AGENTS, MCP_SERVERS
from rag.ingest import load_corpus

app = typer.Typer(help="Inventory of agents, known signal types, and RAG playbooks.", no_args_is_help=True)
console = Console()


@app.command("agents")
def agents_cmd() -> None:
    """List every agent + MCP server the repo ships."""
    tbl = Table(title="GrafanAgent — agents", title_style="bold cyan")
    tbl.add_column("name", style="bold")
    tbl.add_column("kind")
    tbl.add_column("model")
    tbl.add_column("default port")
    tbl.add_column("module")
    for a in AGENTS:
        tbl.add_row(a.name, a.kind, a.model or "—", str(a.default_port), a.module)
    console.print(tbl)

    tbl2 = Table(title="MCP servers", title_style="bold cyan")
    tbl2.add_column("name", style="bold")
    tbl2.add_column("default port")
    tbl2.add_column("module")
    tbl2.add_column("tools")
    for m in MCP_SERVERS:
        tbl2.add_row(m.name, str(m.default_port), m.module, ", ".join(m.tools))
    console.print(tbl2)


@app.command("signals")
def signals_cmd() -> None:
    """List the signal types the router's deterministic rule table recognises."""
    tbl = Table(title="Rule-table signal types (fallback rung)", title_style="bold cyan")
    tbl.add_column("signal_type", style="bold")
    tbl.add_column("→ skill")
    for signal_type, skill in sorted(RULE_TABLE.items()):
        tbl.add_row(signal_type, skill)
    console.print(tbl)
    console.print(
        "\n[dim]New signal types not in this table escalate through the LLM fallback chain "
        "(Haiku → Sonnet → HITL) rather than the rule rung.[/dim]"
    )


@app.command("playbooks")
def playbooks_cmd() -> None:
    """List every RAG playbook plus its signal-type coverage and audience."""
    chunks = load_corpus()
    by_slug: dict[str, dict] = {}
    for c in chunks:
        agg = by_slug.setdefault(
            c.playbook_slug,
            {
                "sections": 0,
                "signal_types": c.metadata.get("signal_types", []),
                "audience": c.metadata.get("audience") or "",
                "channel": c.metadata.get("channel") or "",
            },
        )
        agg["sections"] += 1
    tbl = Table(title="RAG corpus", title_style="bold cyan")
    tbl.add_column("slug", style="bold")
    tbl.add_column("sections")
    tbl.add_column("signal_types")
    tbl.add_column("audience")
    tbl.add_column("channel")
    for slug in sorted(by_slug):
        a = by_slug[slug]
        tbl.add_row(
            slug,
            str(a["sections"]),
            ", ".join(a["signal_types"]) or "—",
            a["audience"][:60],
            a["channel"],
        )
    console.print(tbl)
