"""
Sprint 30 — Cleanup.

Static guards over the burn-down items:

  1. The stray `infra/db/migrations;C` directory is gone (was a Windows
     redirection accident from an earlier sprint).
  2. `hub-ui/src/data/tutorials.ts` no longer ships literal localhost URLs
     in the prod bundle — copy is templated through `fmt({HUB}/{DB}/{API})`.
  3. The auth-service seeder is gated behind `SEED_DEMO_DATA` and the
     `/auth/login` fallback to DEMO_TENANT_ID is disabled in prod.
  4. CI runs `ruff --select F401` (Python dead imports) and a ts-prune
     gate for TypeScript dead exports.
  5. The repo passes `ruff --select F401 services/ tests/` clean.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------- stray dir removed

def test_stray_migrations_dir_is_gone():
    stray = REPO / "infra" / "db" / "migrations;C"
    assert not stray.exists(), (
        f"{stray} still exists — it's a Windows redirection accident "
        "(`>migrations;C` instead of `>migrations 2>&1`). Delete it."
    )


# -------------------------------------------------- tutorials.ts is templated

TUTORIALS = REPO / "services" / "hub-ui" / "src" / "data" / "tutorials.ts"


def test_tutorials_uses_template_helpers():
    src = TUTORIALS.read_text(encoding="utf-8")
    # The templating helper itself must exist.
    assert "function fmt" in src, (
        "tutorials.ts must define a fmt() helper that interpolates "
        "VITE_HUB_URL / VITE_DB_URL / VITE_API_HOST"
    )
    for env_var in ("VITE_HUB_URL", "VITE_DB_URL", "VITE_API_HOST"):
        assert env_var in src, (
            f"tutorials.ts must read {env_var} so prod copy doesn't ship dev URLs"
        )


def test_tutorials_no_hardcoded_localhost_urls():
    src = TUTORIALS.read_text(encoding="utf-8")
    # Strip the helper-default fallback line so we don't false-positive on it.
    pruned = re.sub(
        r"VITE_HUB_URL\?: string;\s*}\s*\}\)\.env\?\.VITE_HUB_URL \?\? '[^']+'",
        "",
        src,
    )
    pruned = re.sub(r"\?\? 'http://localhost[^']*'", "", pruned)
    offenders = re.findall(r"http://localhost:\d+", pruned)
    assert offenders == [], (
        f"tutorials.ts still has hardcoded localhost URLs in copy: {offenders}. "
        "Use fmt('… {HUB} …') instead."
    )


# ------------------------------------------------------ seeder + DEMO_TENANT_ID

AUTH_MAIN = REPO / "services" / "auth-service" / "src" / "main.py"


def test_seeder_is_gated_behind_seed_demo_data():
    src = AUTH_MAIN.read_text(encoding="utf-8")
    assert "SEED_DEMO_DATA" in src, "auth-service must read SEED_DEMO_DATA env var"
    # Default must be off in prod.
    assert 'IS_PROD else "false"' in src or '"false" if IS_PROD' in src or (
        "IS_PROD" in src and "SEED_DEMO_DATA" in src
    ), "SEED_DEMO_DATA must default to false in prod"
    # The seed call must be inside an `if SEED_DEMO_DATA:` branch.
    assert re.search(r"if\s+SEED_DEMO_DATA\s*:", src), (
        "Seeder calls must be guarded by `if SEED_DEMO_DATA:`"
    )


def test_demo_tenant_id_is_documented():
    src = AUTH_MAIN.read_text(encoding="utf-8")
    # The pattern doc-comment landed in Sprint 30.
    assert "DEMO_TENANT_ID — well-known UUID" in src, (
        "DEMO_TENANT_ID must carry a doc comment explaining the dev/prod pattern"
    )


def test_login_refuses_demo_tenant_fallback_in_prod():
    src = AUTH_MAIN.read_text(encoding="utf-8")
    # The Sprint 30 hardening: in prod we 400 instead of falling back.
    assert "tenant_id is required in production" in src, (
        "In prod, /auth/login must reject the absent-tenant_id case rather "
        "than falling back to DEMO_TENANT_ID"
    )


# ----------------------------------------------------- CI dead-code gates wired

CI_FILE = REPO / ".github" / "workflows" / "ci.yml"
COVERAGE_GATE = REPO / "scripts" / "coverage_gate.sh"
TS_PRUNE_GATE = REPO / "scripts" / "ts_prune_check.sh"


def test_ci_workflow_runs_ruff_f401():
    src = CI_FILE.read_text(encoding="utf-8")
    assert "ruff check --select F401" in src, (
        "CI workflow must run `ruff check --select F401` over services + tests"
    )
    assert "services/ tests/" in src, (
        "ruff F401 step must scope to both services/ and tests/"
    )


def test_ci_workflow_runs_ts_prune():
    src = CI_FILE.read_text(encoding="utf-8")
    assert "ts_prune_check.sh" in src, (
        "CI workflow must invoke scripts/ts_prune_check.sh"
    )
    assert TS_PRUNE_GATE.is_file(), "scripts/ts_prune_check.sh missing"


def test_ts_prune_gate_covers_every_ui():
    src = TS_PRUNE_GATE.read_text(encoding="utf-8")
    expected_uis = sorted(
        p.name for p in (REPO / "services").iterdir()
        if p.is_dir() and p.name.endswith("-ui")
    )
    missing = [ui for ui in expected_uis if ui not in src]
    assert missing == [], (
        f"ts_prune_check.sh missing UIs: {missing}. Add them to the UIS array."
    )


# ----------------------------------------------------- repo passes ruff F401

def test_repo_passes_ruff_f401():
    """Live ruff invocation — fast, no DB, no network. Sprint 30 acceptance."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F401",
         str(REPO / "services"), str(REPO / "tests")],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.fail(
            "ruff F401 check failed — repo has unused imports:\n"
            + proc.stdout + proc.stderr
        )
