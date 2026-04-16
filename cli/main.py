"""`grafanagent` CLI entrypoint.

Wires each subcommand as its own Typer app for clean --help output, e.g.:

    grafanagent trigger signal.json
    grafanagent replay signal.json --url http://localhost:8000
    grafanagent list agents
    grafanagent list signals
    grafanagent list playbooks
    grafanagent describe agent router
    grafanagent describe mcp bigquery
    grafanagent eval [--golden-set evals/golden_set.jsonl]

Exposes every agent skill through a unified CLI so operators can trigger,
replay, list, describe, and evaluate runs without hitting the HTTP surface
directly.
"""
from __future__ import annotations

import typer

from cli.commands import describe, eval_cmd, list_cmd, replay, trigger

app = typer.Typer(
    name="grafanagent",
    help="Operate GrafanAgent: trigger signals, inspect agents, run the eval gate.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("trigger", help="POST a signal JSON to the router and print the decision.")(
    trigger.trigger
)
app.command("replay", help="Replay a stored signal (from file) through the router.")(
    replay.replay
)
app.add_typer(list_cmd.app, name="list", help="List agents, known signal types, or playbooks.")
app.add_typer(describe.app, name="describe", help="Describe a single agent or MCP server.")
app.command("eval", help="Run the golden-set evaluation.")(eval_cmd.eval_cmd)


if __name__ == "__main__":  # pragma: no cover
    app()
