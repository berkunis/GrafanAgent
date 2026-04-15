.PHONY: install dev fmt lint test smoke tf-init clean db-up db-down ingest \
        bolt-install bolt-build bolt-test bolt-dev bolt-up bolt-down

install:
	pip install -e ".[dev]"

dev: install
	pip install -e ".[bigquery,slack]"

fmt:
	ruff format .

lint:
	ruff check .

test:
	pytest -q

# Boot each service stub once (emit a span and exit) — verifies wiring.
smoke:
	SMOKE=1 python -m agents.router.main
	SMOKE=1 python -m agents.lifecycle.main
	SMOKE=1 python -m agents.lead_scoring.main
	SMOKE=1 python -m agents.attribution.main
	SMOKE=1 python -m mcp_servers.bigquery.server
	SMOKE=1 python -m mcp_servers.customer_io.server
	SMOKE=1 python -m mcp_servers.slack.server

db-up:
	docker compose up -d pgvector
	@echo "pgvector on localhost:5433 (user/db: grafanagent, pass: grafanagent)"

db-down:
	docker compose down

# Ingest the RAG corpus. Defaults to the in-memory HashEmbedder so it runs
# without credentials; flip to RAG_EMBEDDER=vertex RAG_BACKEND=pgvector for real.
ingest:
	PGVECTOR_DSN=postgresql://grafanagent:grafanagent@localhost:5433/grafanagent \
	  python -m rag.ingest

# ---- Slack Bolt approval app (TypeScript) ----

bolt-install:
	cd apps/slack-approver && npm install

bolt-build: bolt-install
	cd apps/slack-approver && npm run build

bolt-test: bolt-install
	cd apps/slack-approver && npm test

bolt-dev: bolt-install
	cd apps/slack-approver && npm run dev

# Run the Bolt app in docker compose alongside pgvector.
bolt-up:
	docker compose up -d slack-approver
	@echo "slack-approver on http://localhost:3030"

bolt-down:
	docker compose stop slack-approver

tf-init:
	terraform -chdir=infra/terraform init

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
