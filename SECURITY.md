# Security policy

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security problems.

Email **berkunis@digifab.ai** with:
- A description of the issue.
- Steps to reproduce.
- Your assessment of the impact.
- Whether you'd like to be credited once the fix ships.

You'll get an acknowledgement within 72 hours and a status update within 7 days. Fixes for exploitable vulnerabilities ship within 30 days; I'll coordinate disclosure timing with you.

## Scope

GrafanAgent is a portfolio / reference project, not a production service. The code is built as a real-world template — the guardrails (sandbox flags, PII scrubber, secret-manager mounts, Block Kit signing-secret auth) are there because bypassing them in a fork could cause real damage, not because I'm operating a bug-bounty program.

In-scope findings we want to hear about:

- Escape of the Customer.io sandbox guard (`CUSTOMERIO_SANDBOX != 1` somehow still writing real data).
- Any path that persists raw secrets to disk or a trace exporter.
- Prompt-injection vectors in the router, lifecycle, lead-scoring, or attribution agents that can escalate privilege beyond the claim "lead scorer reads BigQuery."
- BigQuery MCP allow-list bypass or PII-redaction bypass.
- Slack signing-secret validation bypass on the Bolt app.
- SQL injection in the RAG pgvector adapter.
- Dependency vulnerabilities with a clear exploit path in our use.

Out of scope:

- Running the demo with real production credentials (see `docs/runbook.md`'s cost-controls section — this is a configuration problem, not a vulnerability).
- Denial of service via expensive prompts (mitigated by `max_instances` + the cost-spike alert, not eliminated).
- Issues in upstream packages (`anthropic`, `@slack/bolt`, etc.) without a GrafanAgent-specific exploit path.
