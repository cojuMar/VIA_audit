"""
Pre-Sprint-21 bug: tenant_id was interpolated into an f-string:
    f"SET app.tenant_id = '{tenant_id}'"
Combined with client-controlled tenant_id, this allowed SQL injection via the
tenant field.

Post-Sprint-21 contract:
  - All SET app.tenant_id calls use set_config($1, true) with a bound parameter.
  - tenant_id is UUID-only (comes from the JWT), never a string the client picks.
  - Any residual injection attempt must produce a harmless error, never side
    effects.
"""
from __future__ import annotations

from jose import jwt as jose_jwt


def _forge_token(tenant_id: str, secret: str = "aegis_dev_jwt_secret_change_in_prod") -> str:
    """Build a JWT whose `tenant_id` claim contains an injection payload."""
    return jose_jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000abc",
            "email": "attacker@evil.com",
            "full_name": "Attacker",
            "role": "end_user",
            "tenant_id": tenant_id,
        },
        secret,
        algorithm="HS256",
    )


def test_notifications_with_injection_tenant_id_does_not_execute(http):
    """
    Even if an attacker forges a JWT whose `tenant_id` claim contains a SQL
    payload, the parameterised set_config must treat it as a literal value.
    Postgres will reject it as a bad UUID; it must NEVER execute as SQL.
    """
    payload = "'; DROP TABLE via_users; --"
    token = _forge_token(payload)
    r = http.get(
        "/auth/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Expect a 4xx/5xx — the important bit is that via_users still exists
    # (validated by the admin login working in other tests).
    assert r.status_code != 200 or r.json() == []


def test_search_with_injection_tenant_id_does_not_execute(http):
    payload = "00000000-0000-0000-0000-000000000001'); DROP TABLE notifications; --"
    token = _forge_token(payload)
    r = http.post(
        "/auth/search",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code != 500
