"""Sanity-check the Dockerfiles + deploy scripts.

We don't try to actually build images here — CI doesn't have a Docker daemon.
These checks catch the cheap failure modes: missing stages, missing COPY of
the code we need, deploy.sh referencing a service that doesn't exist in the
registry loop.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_python_dockerfile_has_shared_service_module_arg():
    df = (ROOT / "Dockerfile").read_text()
    assert "ARG SERVICE_MODULE" in df
    assert "CMD " in df
    assert "${SERVICE_MODULE}" in df


def test_python_dockerfile_copies_every_runtime_package():
    df = (ROOT / "Dockerfile").read_text()
    # Every top-level runtime package should end up in the image. Tests /
    # docs / dashboards are excluded via .dockerignore.
    for pkg in ("observability", "agents", "mcp_servers"):
        assert re.search(rf"COPY\s+{pkg}\s+", df), f"Dockerfile does not COPY {pkg}"


def test_node_dockerfile_has_multistage_build():
    df = (ROOT / "apps/slack-approver/Dockerfile").read_text()
    assert "FROM node:22-alpine AS build" in df
    assert "FROM node:22-alpine AS runtime" in df
    assert "npm run build" in df
    assert "CMD " in df
    assert "dist/server.js" in df


def test_node_dockerfile_prunes_dev_dependencies():
    df = (ROOT / "apps/slack-approver/Dockerfile").read_text()
    assert "npm prune --omit=dev" in df


def test_deploy_sh_declares_every_service():
    sh = (ROOT / "scripts/deploy.sh").read_text()
    for svc in ("router", "lifecycle", "lead-scoring", "attribution"):
        assert f"[{svc}]=" in sh, f"deploy.sh missing agent {svc}"
    for mcp in ("mcp-bigquery", "mcp-customer-io", "mcp-slack"):
        assert f"[{mcp}]=" in sh, f"deploy.sh missing MCP {mcp}"
    assert "slack-approver" in sh


def test_deploy_sh_applies_image_tag_consistently():
    sh = (ROOT / "scripts/deploy.sh").read_text()
    assert "IMAGE_TAG" in sh
    assert "image_tag=${IMAGE_TAG}" in sh


def test_dockerignore_keeps_build_context_lean():
    ignore = (ROOT / ".dockerignore").read_text()
    # Everything that would needlessly inflate the context or leak secrets.
    for pattern in (".git", ".venv", "apps/slack-approver/node_modules", "tests/"):
        assert pattern in ignore, f".dockerignore missing {pattern!r}"


def test_makefile_exposes_deploy_surface():
    mf = (ROOT / "Makefile").read_text()
    for target in ("deploy:", "seed:", "smoke-remote:", "tf-validate:", "auth:"):
        assert target in mf, f"Makefile missing target {target}"
