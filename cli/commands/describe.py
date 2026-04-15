"""`grafanagent describe [agent|mcp] <name>` — detailed view of one service."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.router.fallback import (
    DEFAULT_HAIKU_MODEL,
    DEFAULT_HIGH_CONFIDENCE,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_SONNET_MODEL,
)
from agents.router.rules import RULE_TABLE
from cli._registry import AGENTS, MCP_SERVERS, agent_by_name, mcp_by_name
from mcp_servers.bigquery.security import SecurityPolicy
from rag.ingest import load_corpus

app = typer.Typer(help="Describe one agent or MCP server in detail.", no_args_is_help=True)
console = Console()


@app.command("agent")
def describe_agent(
    name: str = typer.Argument(..., help="router | lifecycle | lead_scoring | attribution"),
) -> None:
    spec = agent_by_name(name)
    if spec is None:
        available = ", ".join(a.name for a in AGENTS)
        raise typer.BadParameter(f"unknown agent '{name}'. Known: {available}")

    tbl = Table(title=f"agent: {spec.name}", title_style="bold cyan", show_header=False)
    tbl.add_column("k", style="dim")
    tbl.add_column("v")
    tbl.add_row("kind", spec.kind)
    tbl.add_row("model", spec.model or "—")
    tbl.add_row("default port", str(spec.default_port))
    tbl.add_row("module", spec.module)
    tbl.add_row("description", spec.description)
    console.print(tbl)

    if spec.name == "router":
        console.print(
            Panel.fit(
                f"Haiku model:  {DEFAULT_HAIKU_MODEL}\n"
                f"Sonnet model: {DEFAULT_SONNET_MODEL}\n"
                f"High-confidence ≥ {DEFAULT_HIGH_CONFIDENCE}  → dispatch on Haiku\n"
                f"Mid-confidence  ≥ {DEFAULT_MIN_CONFIDENCE}  → re-ask Sonnet\n"
                f"Below min       → rule table → HITL",
                title="fallback chain",
                border_style="green",
            )
        )
        rules = Table(title="rule table", show_header=True, border_style="dim")
        rules.add_column("signal_type")
        rules.add_column("→ skill")
        for sig, skill in sorted(RULE_TABLE.items()):
            rules.add_row(sig, skill)
        console.print(rules)

    if spec.name == "lifecycle":
        playbooks = {c.playbook_slug for c in load_corpus()}
        console.print(
            Panel.fit(
                f"Synthesis model: claude-sonnet-4-5\n"
                f"Fan-out legs:    BigQuery user ctx, RAG playbooks, Customer.io memberships\n"
                f"HITL:            gates every draft before Customer.io execution\n"
                f"RAG corpus:      {len(playbooks)} playbooks",
                title="orchestration",
                border_style="green",
            )
        )

    if spec.name == "lead_scoring":
        console.print(
            Panel.fit(
                "Synthesis model: claude-sonnet-4-5\n"
                "Fan-out legs:    BigQuery lead + usage, RAG scoring playbooks\n"
                "HITL:            gates only high-priority SDR alerts\n"
                "                 medium priority fires without a human gate\n"
                "                 low priority drops to nurture queue silently",
                title="orchestration",
                border_style="green",
            )
        )

    if spec.name == "attribution":
        console.print(
            Panel.fit(
                "Synthesis model: claude-sonnet-4-5\n"
                "Fan-out legs:    BigQuery touches + opportunities, RAG attribution playbooks\n"
                "Output:          first_touch, last_touch, multi_touch (weights sum to 1.0)\n"
                "                 + top-driver rationale + three-line verdict\n"
                "HITL:            none — reports post directly to the RevOps channel",
                title="orchestration",
                border_style="green",
            )
        )


@app.command("mcp")
def describe_mcp(
    name: str = typer.Argument(..., help="bigquery | customer_io | slack"),
) -> None:
    spec = mcp_by_name(name)
    if spec is None:
        available = ", ".join(m.name for m in MCP_SERVERS)
        raise typer.BadParameter(f"unknown MCP server '{name}'. Known: {available}")

    tbl = Table(title=f"mcp: {spec.name}", title_style="bold cyan", show_header=False)
    tbl.add_column("k", style="dim")
    tbl.add_column("v")
    tbl.add_row("default port", str(spec.default_port))
    tbl.add_row("module", spec.module)
    tbl.add_row("description", spec.description)
    tbl.add_row("tools", ", ".join(spec.tools))
    console.print(tbl)

    if spec.name == "bigquery":
        pol = SecurityPolicy.from_env()
        console.print(
            Panel.fit(
                f"Allowed datasets:  {', '.join(pol.allowed_datasets)}\n"
                f"Max rows per call: {pol.max_rows}\n"
                f"Read-only:         enforced via sqlglot parse\n"
                f"PII redaction:     column-name match on configured regex",
                title="security guards",
                border_style="green",
            )
        )
