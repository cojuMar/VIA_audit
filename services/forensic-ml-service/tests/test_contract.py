"""
Sprint 29 — forensic-ml-service contract + integration tests.

Anomaly scoring + Benford analysis surface. The /score endpoint is the
core API; reviewer workflows depend on /anomalies/{id}/review.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"

REQUIRED_ROUTES = [
    ("get",   "/health"),
    ("post",  "/score"),
    ("get",   "/anomalies"),
    ("get",   "/anomalies/{score_id}"),
    ("patch", "/anomalies/{score_id}/review"),
    ("get",   "/benford/{entity_id}"),
]


@pytest.mark.parametrize("method,path", REQUIRED_ROUTES)
def test_route_is_declared(method: str, path: str):
    src = MAIN.read_text(encoding="utf-8")
    assert f'@app.{method}("{path}"' in src, (
        f"forensic-ml-service missing required route {method.upper()} {path}"
    )


ML_URL = os.environ.get("FORENSIC_ML_URL")
needs_live = pytest.mark.skipif(
    not ML_URL, reason="FORENSIC_ML_URL not set — skip live integration"
)


@needs_live
def test_health_returns_200():
    import httpx
    r = httpx.get(f"{ML_URL}/health", timeout=5.0)
    assert r.status_code == 200


@needs_live
def test_score_rejects_anonymous():
    import httpx
    r = httpx.post(f"{ML_URL}/score", json={}, timeout=5.0)
    assert r.status_code in (401, 403, 422), (
        f"expected 401/403/422 from anon /score, got {r.status_code}"
    )
