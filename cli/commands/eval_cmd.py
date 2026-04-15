"""`grafanagent eval` — run the golden set in either rule-table or LLM-judge mode.

Two modes:

    --mode rule   (default, offline)
        Deterministic rule-table check. Runs in CI without any API keys.
        Same behaviour as Phase 4.

    --mode llm
        Full LLM pipeline: runs each case through the real router (Haiku →
        Sonnet fallback chain), judges with Sonnet using an explicit rubric,
        and emits `grafanagent_eval_*` metrics to OTel. Requires
        ANTHROPIC_API_KEY; takes ~30s for a 10-case suite at concurrency=3.

Exit codes:
    0  — pass rate ≥ --threshold
    1  — pass rate below threshold
    2  — bad golden set file or missing API key in llm mode
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from evals.golden import GOLDEN_SET_PATH, run as rule_run, summary as rule_summary

console = Console()
err = Console(stderr=True)


def eval_cmd(
    golden_set: Path = typer.Option(
        GOLDEN_SET_PATH,
        "--golden-set",
        "-g",
        help="Path to a golden-set JSONL file.",
    ),
    mode: str = typer.Option(
        "rule",
        "--mode",
        "-m",
        help="rule = deterministic rule-table check; llm = full LLM fallback chain + Sonnet judge.",
    ),
    threshold: float = typer.Option(
        0.85,
        "--threshold",
        help="Pass rate below this exits non-zero. Match the CI gate.",
    ),
    pass_score: int = typer.Option(
        4,
        "--pass-score",
        help="[llm mode] overall judge score ≥ this counts as a pass.",
    ),
    concurrency: int = typer.Option(
        3,
        "--concurrency",
        "-c",
        help="[llm mode] how many cases to judge in parallel.",
    ),
    emit_metrics: bool = typer.Option(
        False,
        "--emit-metrics/--no-emit-metrics",
        help="[llm mode] emit grafanagent_eval_* metrics via OTel.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print every case row, not just failures."
    ),
) -> None:
    if mode == "rule":
        _run_rule(golden_set, threshold, verbose)
    elif mode == "llm":
        _run_llm(
            golden_set=golden_set,
            threshold=threshold,
            pass_score=pass_score,
            concurrency=concurrency,
            emit=emit_metrics,
            verbose=verbose,
        )
    else:
        raise typer.BadParameter(f"unknown mode {mode!r}; expected 'rule' or 'llm'")


# ---------- rule mode (Phase 4 behaviour) ----------


def _run_rule(golden_set: Path, threshold: float, verbose: bool) -> None:
    try:
        results = list(rule_run(golden_set))
    except Exception as exc:  # noqa: BLE001
        err.print(f"[red]failed to load {golden_set}: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    tbl = Table(title=f"Golden set — rule mode ({len(results)} cases)", title_style="bold cyan")
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

    passed, total, rate = rule_summary(results)
    _print_summary_line(passed, total, rate, threshold, mode="rule")
    if rate < threshold:
        raise typer.Exit(code=1)


# ---------- llm mode (Phase 5) ----------


def _run_llm(
    *,
    golden_set: Path,
    threshold: float,
    pass_score: int,
    concurrency: int,
    emit: bool,
    verbose: bool,
) -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        err.print("[red]--mode llm requires ANTHROPIC_API_KEY.[/red]")
        err.print("Use --mode rule for an offline CI check, or export the key.")
        raise typer.Exit(code=2)

    # Imports deferred so rule-mode runs without pulling in Anthropic SDK chains.
    from agents._llm import LLMClient
    from agents.router.fallback import FallbackChain
    from evals.metrics import emit as emit_metrics
    from evals.runner import RunConfig, fallback_chain_router, run_suite
    from observability import init_telemetry

    init_telemetry("grafanagent-eval")

    llm_router = LLMClient(agent="router-eval")
    llm_judge = LLMClient(agent="judge")
    chain = FallbackChain(llm_router)
    router = fallback_chain_router(chain)
    cfg = RunConfig(pass_threshold=pass_score, concurrency=concurrency)

    try:
        results, summary = asyncio.run(
            run_suite(router=router, judge_llm=llm_judge, golden_path=golden_set, cfg=cfg)
        )
    except Exception as exc:  # noqa: BLE001
        err.print(f"[red]eval run failed: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    tbl = Table(title=f"Golden set — llm mode ({summary.total} cases)", title_style="bold cyan")
    tbl.add_column("id", style="bold")
    tbl.add_column("type")
    tbl.add_column("expected")
    tbl.add_column("actual")
    tbl.add_column("overall", justify="right")
    tbl.add_column("issues")
    tbl.add_column("result")
    for r in results:
        if not r.passed or verbose:
            issues = r.error or "; ".join((r.judge.issues if r.judge else []))
            tbl.add_row(
                r.case_id,
                r.signal_type,
                r.expected_skill,
                r.actual_skill or "—",
                str(r.overall_score),
                issues[:80],
                "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]",
            )
    console.print(tbl)

    console.print(
        f"\nmean overall score: [bold]{summary.mean_overall_score:.2f}[/bold] "
        f"(confidence: {summary.mean_confidence_calibration:.2f}, "
        f"rationale: {summary.mean_rationale_quality:.2f})"
    )
    if summary.by_skill:
        sk = Table(title="by skill", title_style="dim")
        sk.add_column("skill")
        sk.add_column("pass_rate", justify="right")
        sk.add_column("mean_overall", justify="right")
        for skill, stats in summary.by_skill.items():
            sk.add_row(
                skill,
                f"{stats['pass_rate']:.0%}",
                f"{stats['mean_overall_score']:.2f}",
            )
        console.print(sk)

    _print_summary_line(summary.passed, summary.total, summary.pass_rate, threshold, mode="llm")

    if emit:
        emit_metrics(
            results=results,
            summary=summary,
            set_name=golden_set.stem,
            mode="llm",
        )
        console.print("[dim]emitted grafanagent_eval_* metrics via OTel.[/dim]")

    if summary.pass_rate < threshold:
        raise typer.Exit(code=1)


def _print_summary_line(passed: int, total: int, rate: float, threshold: float, *, mode: str) -> None:
    style = "green" if rate >= threshold else "red"
    console.print(
        f"\n[{style}]pass rate ({mode}): {passed}/{total} = {rate:.0%}[/{style}]  "
        f"(threshold: {threshold:.0%})"
    )
