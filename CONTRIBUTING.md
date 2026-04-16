# Contributing to GrafanAgent

Thanks for taking a look. The doors are open to fixes, clarifications, and new skill agents. Bigger architectural changes are worth opening an issue on first.

## Dev setup

```bash
git clone https://github.com/berkunis/GrafanAgent.git && cd GrafanAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Optional: TypeScript Slack approver tests
make bolt-install

# Optional: local pgvector for RAG integration runs
make db-up
```

## The test + lint loop

Every PR must pass these three locally before opening:

```bash
pytest -q                 # 145 Python tests, <1s, zero credentials needed
make bolt-test            # 17 TypeScript tests for the Slack Bolt app
ruff check .              # linter; ruff format . to apply fixes
```

`make smoke` boots every service stub once (emits a span and exits) — useful after adding a new service.

`grafanagent eval --mode rule` runs the deterministic rule-table gate the CI workflow gates on. `--mode llm` runs the full Sonnet-judge pipeline and needs `ANTHROPIC_API_KEY`.

## Adding a new skill agent

Follow [`docs/adding_a_new_skill.md`](docs/adding_a_new_skill.md). The template is concrete — the three shipped skill agents (`lifecycle`, `lead_scoring`, `attribution`) each cover a different HITL policy so you'll probably find one that matches your use case.

## Adding a RAG playbook

1. Drop a markdown file in `rag/corpus/<slug>.md` with the same frontmatter as existing playbooks (`slug`, `signal_types`, `audience`, `channel`).
2. Use H2 (`## Trigger`, `## Guardrails`, …) to split the body — the ingester splits on those.
3. `make ingest` to reload the local pgvector store.
4. Add a matching case to `evals/golden_set.jsonl` so the eval gate covers the new signal type.

## Commit conventions

- One commit per logical change. Small is better.
- The body explains **why** first, **what** second. Assume the reader is coming to the diff six months later.
- Every commit includes a `Co-Authored-By:` line if AI-assisted; see recent commits for the shape.

Claude Code does most of this repo's typing. The authorship model: every PR still has a human owner who reads every line, writes the "why" in the commit message, and answers questions on the review. See [`docs/DESIGN.md`](docs/DESIGN.md) for why that matters to us.

## Reporting bugs

For non-security issues: open a GitHub issue with steps to reproduce, the observed behaviour, and what you expected. Include the relevant trace id if you're already running with OTel → Grafana Cloud; we can pull the prompt + completion off the span.

For security issues: see [`SECURITY.md`](SECURITY.md).

## Code of conduct

Be kind. Explain your reasoning. Don't ship code you wouldn't sign your name to.
