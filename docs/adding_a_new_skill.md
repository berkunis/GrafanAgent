# Adding a new skill agent

> Stub. Will be filled in once the router + first agent land.

Outline:
1. Create `agents/<skill>/main.py` calling `agents._base.run("<skill>")`.
2. Register the skill in the router's classifier prompt + structured-output schema.
3. Add MCP tool wiring as needed.
4. Extend `evals/golden_set.jsonl` with at least 3 representative signals.
5. Add a Cloud Run service to `infra/terraform/` (cloud_run module).
6. Verify trace shows up in Tempo with correct service.name.
