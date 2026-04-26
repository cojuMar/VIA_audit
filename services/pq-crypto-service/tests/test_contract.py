"""
Sprint 29 — pq-crypto-service contract + integration tests.

Kyber KEM + Dilithium signature surface. The crypto primitives are the
service's core value, so we assert all 6 primitive endpoints are still
declared.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"

REQUIRED_ROUTES = [
    ("get",  "/health"),
    ("post", "/kyber/keypair"),
    ("post", "/kyber/encapsulate"),
    ("post", "/kyber/decapsulate"),
    ("post", "/dilithium/keypair"),
    ("post", "/dilithium/sign"),
    ("post", "/dilithium/verify"),
    ("get",  "/keys/{tenant_id}"),
]


@pytest.mark.parametrize("method,path", REQUIRED_ROUTES)
def test_route_is_declared(method: str, path: str):
    src = MAIN.read_text(encoding="utf-8")
    assert f'@app.{method}("{path}"' in src, (
        f"pq-crypto-service missing required route {method.upper()} {path}"
    )


PQ_URL = os.environ.get("PQ_CRYPTO_URL")
needs_live = pytest.mark.skipif(
    not PQ_URL, reason="PQ_CRYPTO_URL not set — skip live integration"
)


@needs_live
def test_health_returns_200():
    import httpx
    r = httpx.get(f"{PQ_URL}/health", timeout=5.0)
    assert r.status_code == 200


@needs_live
def test_keypair_rejects_anonymous():
    """Generating a keypair must not be a drive-by — auth required."""
    import httpx
    r = httpx.post(f"{PQ_URL}/kyber/keypair", json={}, timeout=5.0)
    assert r.status_code in (401, 403), (
        f"expected 401/403 from /kyber/keypair anon, got {r.status_code}"
    )
