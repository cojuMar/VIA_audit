"""Sprint 21 regression test fixtures."""
from __future__ import annotations

import os
import httpx
import pytest


AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "http://localhost:3010")


@pytest.fixture(scope="session")
def base_url() -> str:
    return AUTH_BASE_URL


@pytest.fixture()
def http(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client


def _login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(http) -> str:
    return _login(http, "admin@via.com", "admin123")


@pytest.fixture()
def end_user_token(http) -> str:
    return _login(http, "user@via.com", "user123")


@pytest.fixture()
def other_tenant_id() -> str:
    """A fabricated tenant UUID that the authenticated user does NOT belong to."""
    return "ffffffff-ffff-ffff-ffff-ffffffffffff"
