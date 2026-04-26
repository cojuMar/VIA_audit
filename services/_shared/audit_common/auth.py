"""
audit_common.auth — JWT validation and `get_current_user` dependency.

Every backend service used to roll its own copy of "decode the bearer token,
look up the tenant_id, raise 401 on failure". This is the canonical version.

The `JWT_SECRET` env var must match what the auth-service signs with — see
docker-compose.yml's `JWT_SECRET` and Sprint 25's `${JWT_SECRET:?…}` guard
in the prod overlay.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header, HTTPException

JWT_ALGO = "HS256"


@dataclass(frozen=True)
class CurrentUser:
    """The slice of a validated JWT every service actually consumes."""

    user_id: str
    tenant_id: str
    role: str
    email: str | None = None
    raw_claims: dict[str, Any] | None = None


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        # Fail closed in prod — Sprint 25's overlay also enforces this at
        # the docker-compose layer, but a service lifted out of compose
        # (CLI tools, batch jobs) shouldn't quietly accept "" either.
        raise RuntimeError(
            "JWT_SECRET is unset — refusing to validate tokens with an empty secret"
        )
    return secret


def decode_token(token: str) -> CurrentUser:
    """Decode + validate a bearer token. Raises HTTPException 401 on failure."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    user_id = claims.get("sub") or claims.get("user_id")
    tenant_id = claims.get("tenant_id")
    role = claims.get("role", "end_user")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="token missing sub/tenant_id")

    return CurrentUser(
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        role=str(role),
        email=claims.get("email"),
        raw_claims=claims,
    )


def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """FastAPI dependency. Reads `Authorization: Bearer <token>` and validates."""
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="expected Bearer scheme")
    token = authorization.split(" ", 1)[1].strip()
    return decode_token(token)
