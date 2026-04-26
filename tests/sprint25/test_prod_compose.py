"""
Sprint 25 — production-overlay guards.

These tests parse the merged docker-compose configuration with the prod
overlay applied and assert the four invariants the sprint set:

  1. The internal network is isolated.
  2. Only UI services have host port bindings.
  3. Every required secret uses ${VAR:?…} fail-closed syntax (no silent dev
     defaults survive into prod).
  4. The dev seeder is off and hub-ui waits on its upstreams.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
PROD = REPO / "docker-compose.prod.yml"
ENV_EXAMPLE = REPO / ".env.prod.example"

# Filled-in test env so `docker compose config` doesn't error during the merge.
TEST_ENV = {
    "POSTGRES_PASSWORD": "test_pw",
    "POSTGRES_APP_PASSWORD": "test_app_pw",
    "VAULT_ROOT_TOKEN": "test_vault_token",
    "MINIO_ROOT_USER": "test_minio_user",
    "MINIO_ROOT_PASSWORD": "test_minio_pw",
    "JWT_SECRET": "test_jwt_secret_32_bytes_min_xxxxxxxxxxxxx",
    "CORS_ORIGINS": "https://test.example.com",
    "ENCRYPTION_KEY": "test_encryption_key_32bytes_xxxxxxxxxxxx",
}

# UIs are the only services allowed to publish ports in prod. Update this set
# if a new UI service is added to docker-compose.yml.
ALLOWED_PORT_PUBLISHERS = {
    "dashboard-ui", "hub-ui", "trust-portal-ui", "monitoring-ui",
    "people-ui", "pbc-ui", "framework-ui", "tprm-ui",
    "integration-ui", "ai-agent-ui", "risk-ui",
    "audit-planning-ui", "esg-board-ui", "mobile-app",
}


def _docker_compose_available() -> bool:
    return shutil.which("docker") is not None


pytestmark = pytest.mark.skipif(
    not _docker_compose_available(),
    reason="docker CLI not available — skip merged-config tests",
)


# ----------------------------------------------------------- helpers

def _merged_config(env: dict[str, str] | None = None) -> dict:
    """Return the rendered/merged compose config as a dict."""
    full_env = os.environ.copy()
    full_env.update(env or TEST_ENV)
    proc = subprocess.run(
        [
            "docker", "compose",
            "-f", str(COMPOSE),
            "-f", str(PROD),
            "config",
        ],
        capture_output=True, text=True, env=full_env,
    )
    assert proc.returncode == 0, (
        f"docker compose config failed: {proc.stderr}"
    )
    return yaml.safe_load(proc.stdout)


# ----------------------------------------------------------- structure

def test_prod_overlay_exists():
    assert PROD.exists(), "docker-compose.prod.yml missing"


def test_env_prod_example_exists_and_has_required_keys():
    assert ENV_EXAMPLE.exists(), ".env.prod.example missing"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in [
        "POSTGRES_PASSWORD", "POSTGRES_APP_PASSWORD", "VAULT_ROOT_TOKEN",
        "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "JWT_SECRET",
        "CORS_ORIGINS", "ENCRYPTION_KEY",
    ]:
        assert re.search(rf"^{key}=", text, re.M), (
            f".env.prod.example missing required key {key}"
        )


def test_env_prod_is_gitignored():
    text = (REPO / ".gitignore").read_text(encoding="utf-8")
    # `.env` and `.env.*` are both fine; either matches `.env.prod`.
    assert any(p in text for p in (".env.prod", ".env.*", ".env*")), (
        ".env.prod not covered by .gitignore"
    )


# ---------------------------------------------------------- fail-closed

def test_prod_overlay_refuses_to_render_without_secrets():
    """Without any of the required env vars, `docker compose config` exits 1."""
    # Preserve OS env (docker on Windows needs SystemRoot/ProgramData/etc.)
    # but scrub the specific secrets the overlay requires.
    scrubbed = os.environ.copy()
    for k in TEST_ENV:
        scrubbed.pop(k, None)
    proc = subprocess.run(
        [
            "docker", "compose",
            "-f", str(COMPOSE),
            "-f", str(PROD),
            "--env-file", os.devnull,
            "config",
        ],
        capture_output=True, text=True, env=scrubbed,
    )
    assert proc.returncode != 0, (
        "Prod overlay rendered successfully WITHOUT required secrets — "
        f"fail-closed broken. STDOUT: {proc.stdout[:500]}"
    )
    # Error should name at least one of the required vars.
    combined = (proc.stdout + proc.stderr).lower()
    assert any(
        v.lower() in combined for v in
        ("postgres_password", "jwt_secret", "vault_root_token")
    ), f"Expected a 'required variable' error; got: {proc.stderr[:500]}"


# --------------------------------------------------------- merged-config

def test_internal_network_is_isolated_in_prod():
    cfg = _merged_config()
    nets = cfg.get("networks") or {}
    internal = nets.get("aegis-internal") or {}
    assert internal.get("internal") is True, (
        "aegis-internal must be `internal: true` in prod overlay"
    )


def test_only_ui_services_publish_ports_in_prod():
    cfg = _merged_config()
    offenders: list[str] = []
    for name, svc in (cfg.get("services") or {}).items():
        if not svc.get("ports"):
            continue
        if name not in ALLOWED_PORT_PUBLISHERS:
            offenders.append(f"{name} → {svc['ports']}")
    assert offenders == [], (
        f"Backend services still bind host ports in prod: {offenders}. "
        "Add `ports: []` to docker-compose.prod.yml for each."
    )


def test_seed_demo_data_is_off_in_prod():
    cfg = _merged_config()
    auth = (cfg.get("services") or {}).get("auth-service") or {}
    env = auth.get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    seed = str(env.get("SEED_DEMO_DATA", "")).lower()
    assert seed in ("false", "0", "no", ""), (
        f"SEED_DEMO_DATA must be off in prod, got {seed!r}"
    )


def test_hub_ui_waits_on_upstreams_healthy_in_prod():
    cfg = _merged_config()
    hub = (cfg.get("services") or {}).get("hub-ui") or {}
    deps = hub.get("depends_on") or {}
    # docker compose config normalises the long form
    assert isinstance(deps, dict), f"hub-ui.depends_on not normalised: {deps}"
    for upstream in ("auth-service", "dashboard-service"):
        cond = deps.get(upstream, {}).get("condition")
        assert cond == "service_healthy", (
            f"hub-ui must wait on {upstream} with service_healthy in prod, "
            f"got {cond!r}"
        )


def test_heavy_infra_services_have_resource_limits_in_prod():
    cfg = _merged_config()
    services = cfg.get("services") or {}
    required = [
        "postgres", "timescaledb", "kafka", "minio", "mlflow",
        "zk-proof-worker", "forensic-ml-service", "rag-pipeline-service",
    ]
    missing = []
    for s in required:
        deploy = services.get(s, {}).get("deploy") or {}
        limits = (deploy.get("resources") or {}).get("limits") or {}
        if "memory" not in limits:
            missing.append(s)
    assert not missing, (
        f"Heavy services missing memory limit in prod overlay: {missing}"
    )
