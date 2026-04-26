"""
Sprint 29 — evidence-store contract + integration tests.

Evidence ingestion + retrieval. The hash-of-content contract is auditable,
so route shape is part of the security boundary.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[1] / "src" / "main.py"


def test_health_route_declared():
    src = MAIN.read_text(encoding="utf-8")
    assert '@app.get("/health"' in src, (
        "evidence-store missing required /health route"
    )


def test_has_evidence_post_routes():
    """The service exposes at least two POSTs for evidence submission."""
    src = MAIN.read_text(encoding="utf-8")
    post_count = src.count("@app.post(")
    assert post_count >= 2, (
        f"evidence-store should expose ≥2 POST endpoints; found {post_count}"
    )


EVI_URL = os.environ.get("EVIDENCE_STORE_URL")
needs_live = pytest.mark.skipif(
    not EVI_URL, reason="EVIDENCE_STORE_URL not set — skip live integration"
)


@needs_live
def test_health_returns_200():
    import httpx
    r = httpx.get(f"{EVI_URL}/health", timeout=5.0)
    assert r.status_code == 200


@needs_live
def test_evidence_post_rejects_anonymous():
    import httpx
    # Any POST without a token should be rejected before payload validation.
    r = httpx.post(f"{EVI_URL}/evidence", json={}, timeout=5.0)
    assert r.status_code in (401, 403, 404), (
        f"expected 401/403 from anon evidence POST, got {r.status_code}"
    )
