"""`grafanagent eval` — run the golden set and report the pass rate.

Phase 4 runs the deterministic rule-table check (catches renamed signal types
and un-mapped rules). Phase 5 layers an LLM-as-judge on top and pushes results
into Mimir so a Grafana alert can fire on regression.

Exit codes:
    0  — pass rate ≥ threshold
    1  — pass rate below threshold
    2  — bad golden set file
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from evals.golden import GOLDEN_SET_PATH, run, summary

console = Console()
err = Console(stderr=True)


def eval_cmd(
    golden_set: Path = typer.Option(
        GOLDEN_SET_PATH,
        "--golden-set",
        "-g",
        help="Path to a golden-set JSONL file.",
    ),
    threshold: float = typer.Option(
        0.85,
        "--threshold",
        help="Pass rate below this exits non-zero. Match the CI gate.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print every case row, not just failures."
    ),
) -> None:
    try:
        results = list(run(golden_set))
    except Exception as exc:  # noqa: BLE001
        err.print(f"[red]failed to load {golden_set}: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    tbl = Table(title=f"Golden set ({len(results)} cases)", title_style="bold cyan")
    tbl.add_column("id", style="bold")
    tbl.add_column("type")
    tbl.add_column("expected")
    tbl.add_column("actual")
    tbl.add_column("result")

    for r in results:
        if not r.passed or verbose:
            tbl.add_row(
                r.case.id,
                r.case.signal.get("type", ""),
                r.case.expected_skill,
                r.actual_skill or "—",
                "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]",
            )
    console.print(tbl)

    passed, total, rate = summary(results)
    style = "green" if rate >= threshold else "red"
    console.print(
        f"\n[{style}]pass rate: {passed}/{total} = {rate:.0%}[/{style}]  "
        f"(threshold: {threshold:.0%})"
    )

    if rate < threshold:
        raise typer.Exit(code=1)
