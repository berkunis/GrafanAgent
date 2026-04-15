# Single image template — every agent and MCP server builds from this.
# Pick the entrypoint at build time:
#   docker build --build-arg SERVICE_MODULE=agents.router.main -t grafanagent-router .
FROM python:3.12-slim

ARG SERVICE_MODULE
ENV SERVICE_MODULE=${SERVICE_MODULE}
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY observability ./observability
COPY agents ./agents
COPY mcp_servers ./mcp_servers

RUN pip install --upgrade pip && pip install -e .

# Cloud Run injects PORT.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "python -m ${SERVICE_MODULE}"]
