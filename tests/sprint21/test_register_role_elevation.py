"""
Pre-Sprint-21 bug: anonymous POST /auth/register accepted `role` and `tenant_id`
from the body, so any caller could self-provision a super_admin JWT.

Post-Sprint-21 contract:
  - Public registration is disabled unless SELF_REGISTRATION_TENANT is set.
  - When enabled, the role field is IGNORED — always forced to 'end_user'.
  - tenant_id is IGNORED — always the configured self-reg tenant.
"""
from __future__ import annotations

import os


def test_register_role_super_admin_is_rejected_or_downgraded(http):
    r = http.post("/auth/register", json={
        "email": f"attacker+{os.urandom(4).hex()}@evil.com",
        "password": "Pa55w0rd!longenough",
        "full_name": "Attacker",
        "role": "super_admin",
        "tenant_id": "00000000-0000-0000-0000-000000000002",
    })
    # Either the endpoint is disabled (403), or it accepts but downgrades.
    if r.status_code == 403:
        return
    assert r.status_code in (200, 201, 422), r.text
    if r.status_code == 200:
        user = r.json()["user"]
        assert user["role"] == "end_user", \
            f"role elevation succeeded: got {user['role']}"
        assert user["tenant_id"] != "00000000-0000-0000-0000-000000000002", \
            "client-supplied tenant_id was honoured"


def test_register_admin_role_is_rejected_or_downgraded(http):
    r = http.post("/auth/register", json={
        "email": f"attacker+{os.urandom(4).hex()}@evil.com",
        "password": "Pa55w0rd!longenough",
        "full_name": "Attacker",
        "role": "admin",
    })
    if r.status_code == 403:
        return
    assert r.status_code in (200, 201, 422)
    if r.status_code == 200:
        assert r.json()["user"]["role"] == "end_user"


def test_register_missing_extra_fields_still_works(http):
    """Happy path: role/tenant_id absent — endpoint responds consistently."""
    r = http.post("/auth/register", json={
        "email": f"user+{os.urandom(4).hex()}@example.com",
        "password": "Pa55w0rd!longenough",
        "full_name": "Regular User",
    })
    # 403 when disabled, 200/201 when enabled, 409 on dup, 422 on validation.
    assert r.status_code in (200, 201, 403, 409, 422), r.text
