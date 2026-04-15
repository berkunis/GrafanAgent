"""Structural tests for the Terraform stack.

We can't run `terraform validate` in CI without a terraform binary in the
PATH, but we can assert:

  - Every module has versions.tf + main.tf.
  - Every module declares the google provider pinned to a compatible range.
  - The root main.tf instantiates every module we claim to ship.
  - Brace counts balance (catches the worst class of copy-paste error).
  - Every declared tfvars variable has a description (keeps docs honest).
"""
from __future__ import annotations

import re
from pathlib import Path

TF_DIR = Path(__file__).resolve().parent.parent / "infra" / "terraform"

EXPECTED_MODULES = {
    "bigquery",
    "cloudsql",
    "artifact_registry",
    "pubsub",
    "secret_manager",
    "cloud_run_service",
}


def _read_module(name: str) -> dict[str, str]:
    mod = TF_DIR / "modules" / name
    assert mod.is_dir(), f"missing module directory: {mod}"
    out: dict[str, str] = {}
    for tf in mod.glob("*.tf"):
        out[tf.name] = tf.read_text()
    return out


def test_every_expected_module_exists():
    for name in EXPECTED_MODULES:
        files = _read_module(name)
        assert "versions.tf" in files, f"{name} missing versions.tf"
        assert "main.tf" in files, f"{name} missing main.tf"


def test_every_module_pins_google_provider():
    for name in EXPECTED_MODULES:
        files = _read_module(name)
        versions = files["versions.tf"]
        assert "hashicorp/google" in versions, f"{name} does not declare google provider"
        assert re.search(r'version\s*=\s*"~>\s*6\.\d+"', versions), (
            f"{name} google provider pin is not ~> 6.x"
        )


def test_brace_balance_in_every_tf_file():
    """Catches the single biggest class of hand-edit breakage."""
    for tf in TF_DIR.rglob("*.tf"):
        text = tf.read_text()
        # Strip strings so `{` inside a string literal doesn't trip the count.
        stripped = re.sub(r'"([^"\\]|\\.)*"', '""', text)
        open_count = stripped.count("{")
        close_count = stripped.count("}")
        assert open_count == close_count, (
            f"{tf.relative_to(TF_DIR)}: unbalanced braces ({open_count} open, {close_count} close)"
        )


def test_root_main_instantiates_every_service():
    main = (TF_DIR / "main.tf").read_text()
    for svc in ["router", "lifecycle", "lead_scoring", "attribution"]:
        assert f'module "agent_{svc}"' in main, f"root main.tf does not instantiate agent_{svc}"
    for mcp in ["bigquery", "customer_io", "slack"]:
        assert f'module "mcp_{mcp}"' in main, f"root main.tf does not instantiate mcp_{mcp}"
    assert 'module "slack_approver"' in main
    assert 'module "pubsub"' in main
    assert 'module "artifact_registry"' in main
    assert 'module "secret_manager"' in main


def test_every_variable_has_a_description():
    for tf in TF_DIR.rglob("variables.tf"):
        text = tf.read_text()
        # Find every variable block's body and check it mentions `description`.
        for match in re.finditer(r'variable\s+"([^"]+)"\s*\{([^}]+)\}', text, re.DOTALL):
            name, body = match.group(1), match.group(2)
            assert "description" in body, (
                f"{tf.relative_to(TF_DIR)}: variable {name!r} has no description"
            )


def test_tfvars_example_is_valid():
    example = (TF_DIR / "terraform.tfvars.example").read_text()
    assert "project_id" in example
    assert "enable_deploy" in example
    assert "image_tag" in example
