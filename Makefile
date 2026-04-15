.PHONY: install dev fmt lint test smoke tf-init clean

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

tf-init:
	terraform -chdir=infra/terraform init

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
