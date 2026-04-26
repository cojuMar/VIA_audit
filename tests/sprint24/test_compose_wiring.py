"""
Sprint 24 — infra wiring guards.

These are static / lint-style tests that parse docker-compose.yml and assert
the defects identified in the Sprint 20 code review have been fixed and
won't silently regress.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ ports

def test_no_rag_pipeline_port_3010_in_urls(compose):
    """rag-pipeline-service listens on 3008; no other service should URL it as 3010."""
    offenders: list[str] = []
    for name, svc in (compose.get("services") or {}).items():
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env if "=" in e)
        for k, v in env.items():
            if isinstance(v, str) and "rag-pipeline-service:3010" in v:
                offenders.append(f"{name}.{k}={v}")
    assert offenders == [], f"Stale rag-pipeline:3010 refs: {offenders}"


def test_no_framework_service_port_3012_in_urls(compose):
    """framework-service listens on 3013; 3012 collides with pq-crypto-service."""
    offenders: list[str] = []
    for name, svc in (compose.get("services") or {}).items():
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env if "=" in e)
        for k, v in env.items():
            if isinstance(v, str) and "framework-service:3012" in v:
                offenders.append(f"{name}.{k}={v}")
    assert offenders == [], f"Stale framework-service:3012 refs: {offenders}"


def test_no_pgbouncer_port_5432_in_urls(compose):
    """PgBouncer listens on 6432 (5432 is direct-postgres)."""
    offenders: list[str] = []
    for name, svc in (compose.get("services") or {}).items():
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env if "=" in e)
        for k, v in env.items():
            if isinstance(v, str) and "pgbouncer:5432" in v:
                offenders.append(f"{name}.{k}={v}")
    assert offenders == [], f"pgbouncer:5432 (wrong port) refs: {offenders}"


# --------------------------------------------------------------- healthchecks

REQUIRED_HEALTHCHECKS = {
    "postgres", "pgbouncer", "timescaledb", "zookeeper", "kafka",
    "redis", "vault",
}


def test_infrastructure_services_have_healthchecks(compose):
    missing = [
        s for s in REQUIRED_HEALTHCHECKS
        if s in (compose.get("services") or {})
        and not (compose["services"][s].get("healthcheck"))
    ]
    assert missing == [], f"Infra services missing healthcheck: {missing}"


# ---------------------------------------------------------- kafka coupling

def test_dashboard_does_not_wait_on_kafka_consumers_for_health(compose):
    """
    dashboard-service talks to forensic-ml/rag-pipeline over Kafka (async),
    so it must NOT wait for service_healthy on them — that creates a startup
    deadlock when those services are slow to warm.
    """
    dep = compose["services"]["dashboard-service"].get("depends_on") or {}
    for target in ("forensic-ml-service", "rag-pipeline-service"):
        cond = (
            dep.get(target, {}).get("condition") if isinstance(dep, dict) else None
        )
        assert cond != "service_healthy", (
            f"dashboard-service waits on {target} with service_healthy; "
            "must be service_started (or removed)."
        )


# --------------------------------------------------------------- flyway

def test_flyway_migrate_service_defined(compose):
    svc = (compose.get("services") or {}).get("db-migrate")
    assert svc is not None, "db-migrate (Flyway) service missing from compose"
    assert "flyway" in svc.get("image", ""), "db-migrate must use the Flyway image"
    assert "migrate" in str(svc.get("command", "")), (
        "db-migrate must invoke flyway migrate"
    )


# --------------------------------------------------------------- start.ps1

def test_start_ps1_does_not_swallow_migration_errors():
    text = (REPO / "start.ps1").read_text(encoding="utf-8")
    # The footgun was `-q 2>&1 || true` on the psql call inside the inline sh.
    assert "|| true" not in text, (
        "start.ps1 still contains '|| true' which silently swallows migration "
        "errors. Remove it and propagate the exit code."
    )


# --------------------------------------------------------------- makefile

def test_makefile_has_required_targets():
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in ("build:", "up:", "down:", "migrate:", "test:"):
        assert target in mk, f"Makefile missing required target '{target}'"
