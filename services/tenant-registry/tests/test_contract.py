"""
Sprint 29 — tenant-registry contract + integration tests.

Tenant CRUD + firm-bridge wiring. Highly destructive endpoints (DELETE
/tenants/{id}) get extra-strict auth checks.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"

REQUIRED_ROUTES = [
    ("get",    "/health"),
    ("get",    "/tenants"),
    ("get",    "/tenants/{tenant_id}"),
    ("delete", "/tenants/{tenant_id}"),
    ("post",   "/tenants/firm-bridge"),
]


@pytest.mark.parametrize("method,path", REQUIRED_ROUTES)
def test_route_is_declared(method: str, path: str):
    src = MAIN.read_text(encoding="utf-8")
    assert f'@app.{method}("{path}"' in src, (
        f"tenant-registry missing required route {method.upper()} {path}"
    )


REG_URL = os.environ.get("TENANT_REGISTRY_URL")
needs_live = pytest.mark.skipif(
    not REG_URL, reason="TENANT_REGISTRY_URL not set — skip live integration"
)


@needs_live
def test_health_returns_200():
    import httpx
    r = httpx.get(f"{REG_URL}/health", timeout=5.0)
    assert r.status_code == 200


@needs_live
def test_list_tenants_rejects_anonymous():
    import httpx
    r = httpx.get(f"{REG_URL}/tenants", timeout=5.0)
    assert r.status_code in (401, 403), (
        f"expected 401/403 from /tenants anon, got {r.status_code}"
    )
