"""Phase 9 narrative + governance files — asserts the polished surfaces ship
with the repo and stay consistent with each other (pyproject license, README
phase table, DESIGN coverage of every shipped decision area)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_license_file_exists_and_is_mit():
    license_text = (ROOT / "LICENSE").read_text()
    assert "MIT License" in license_text
    assert "Isil Berkun" in license_text
    # pyproject declares MIT — the file must agree.
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'license = { text = "MIT" }' in pyproject


def test_contributing_and_security_files_ship():
    for name in ("CONTRIBUTING.md", "SECURITY.md"):
        p = ROOT / name
        assert p.is_file(), f"missing top-level {name}"
        body = p.read_text()
        assert len(body) > 500, f"{name} is suspiciously short"


def test_contributing_references_real_commands():
    text = (ROOT / "CONTRIBUTING.md").read_text()
    # Every command we advertise must actually work. If any of these change in
    # the Makefile, update the doc in the same PR.
    for cmd in ("pytest -q", "make bolt-test", "ruff check .", "make smoke",
                "grafanagent eval"):
        assert cmd in text, f"CONTRIBUTING missing command: {cmd}"


def test_design_doc_covers_every_phase_area():
    text = (ROOT / "docs/DESIGN.md").read_text()
    # Each shipped phase gets at least one named decision section in DESIGN.md.
    # The exact titles are stable; they serve as anchor links in the blog post
    # and the runbook.
    required_sections = {
        "Why MCP",
        "Model tiering",
        "fallback chain",
        "Parallel fan-out",
        "pgvector",
        "TypeScript",
        "Eval as code",
        "Cache-aware cost model",
        "Per-signal attribution",
        "Cloud Run over Cloud Functions",
        "revision cutover",
        "Secret values never in Terraform",
        "Pub/Sub DLQ",
        "grafanagent` CLI",
    }
    missing = {title for title in required_sections if title not in text}
    assert not missing, f"DESIGN.md missing sections: {missing}"


def test_readme_phase_table_shows_all_phases_shipped():
    text = (ROOT / "README.md").read_text()
    # The build status table must list every phase with a shipped state.
    # Any "⏳" entries mean the header line is stale.
    for phase in range(10):
        row = re.search(rf"^\|\s*{phase}\s*\|", text, re.MULTILINE)
        assert row, f"README build-status table missing row for phase {phase}"
    assert "⏳" not in text, "README build-status table still has pending phases"


def test_readme_links_the_blog_post():
    text = (ROOT / "README.md").read_text()
    assert "docs/blog/building-ai-agents-with-lgtm.md" in text


def test_blog_post_ships():
    p = ROOT / "docs/blog/building-ai-agents-with-lgtm.md"
    assert p.is_file()
    body = p.read_text()
    # Length sanity — the blog is ~1500 words; a trivial stub would be much shorter.
    assert len(body.split()) > 800, "blog post is shorter than expected"


def test_first_issues_seed_list_exists():
    p = ROOT / "docs/FIRST_ISSUES.md"
    assert p.is_file()
    # Five seed ideas, numbered.
    body = p.read_text()
    assert "## 1." in body
    assert "## 5." in body


def test_readme_has_ci_and_license_badges():
    text = (ROOT / "README.md").read_text()
    assert "[![CI]" in text
    assert "[![License: MIT]" in text
    assert "[![Built with Claude Code]" in text
