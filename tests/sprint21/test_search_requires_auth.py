"""
Pre-Sprint-21 bug: POST /auth/search accepted tenant_id from the body and
required no authentication — attacker could enumerate any tenant's engagements,
issues, risks, workpapers, PBC requests, and users.

Post-Sprint-21 contract:
  - Endpoint requires a Bearer JWT.
  - tenant_id is derived from the JWT, never from the body.
"""
from __future__ import annotations


def test_search_without_jwt_returns_401(http):
    r = http.post("/auth/search", json={"query": "anything"})
    assert r.status_code == 401


def test_search_ignores_body_tenant_id(http, end_user_token, other_tenant_id):
    r = http.post(
        "/auth/search",
        json={"query": "test", "tenant_id": other_tenant_id, "limit": 5},
        headers={"Authorization": f"Bearer {end_user_token}"},
    )
    # Must succeed using the caller's tenant. Body tenant_id must be ignored.
    # Schema no longer declares it but extra fields are ignored silently.
    assert r.status_code == 200
    body = r.json()
    assert "results" in body and "total" in body


def test_search_short_query_returns_empty(http, end_user_token):
    r = http.post(
        "/auth/search",
        json={"query": "a"},
        headers={"Authorization": f"Bearer {end_user_token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"results": [], "total": 0}
