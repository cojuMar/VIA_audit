"""
Sprint 29 — pam-broker contract + integration tests.

PAM Broker mediates short-lived auditor credentials via Vault. Treat its
HTTP surface as a frozen API: any rename here breaks the auth-service
flow. Static asserts run unconditionally; integration asserts run when
PAM_BROKER_URL points at a live instance.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"

REQUIRED_ROUTES = [
    ("get",    "/health"),
    ("get",    "/access/requests"),
    ("get",    "/access/audit-log"),
]


@pytest.mark.parametrize("method,path", REQUIRED_ROUTES)
def test_route_is_declared(method: str, path: str):
    src = MAIN.read_text(encoding="utf-8")
    assert f'@app.{method}("{path}"' in src, (
        f"pam-broker missing required route {method.upper()} {path}"
    )


PAM_URL = os.environ.get("PAM_BROKER_URL")
needs_live = pytest.mark.skipif(
    not PAM_URL, reason="PAM_BROKER_URL not set — skip live integration"
)


@needs_live
def test_health_returns_200():
    import httpx
    r = httpx.get(f"{PAM_URL}/health", timeout=5.0)
    assert r.status_code == 200


@needs_live
def test_protected_route_rejects_missing_token():
    """`/access/requests` must reject anonymous callers."""
    import httpx
    r = httpx.get(f"{PAM_URL}/access/requests", timeout=5.0)
    assert r.status_code in (401, 403), (
        f"expected 401/403 from /access/requests anon, got {r.status_code}"
    )
