"""
Sprint 28 — unit tests for the audit_common helpers themselves.

Pure-Python tests; no DB, no network. Validates:
  - tenant_conn refuses an empty tenant_id (fail closed, not silent select-zero)
  - JWT decode rejects missing JWT_SECRET (fail closed in prod)
  - JWT decode round-trips a valid claim set
  - HTTPException subclasses freeze the right status code
  - Structured logger emits JSON with bound tenant_id / request_id
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "_shared"))


# ---------------------------------------------------------------- db.tenant_conn

@pytest.mark.asyncio
async def test_tenant_conn_rejects_empty_tenant_id():
    from audit_common.db import tenant_conn

    class _FakePool:
        async def acquire(self):  # pragma: no cover — never reached
            raise AssertionError("pool.acquire should not be called")

    with pytest.raises(ValueError, match="non-empty tenant_id"):
        async with tenant_conn(_FakePool(), ""):
            pass


# ---------------------------------------------------------------- errors

def test_error_subclasses_have_frozen_status_codes():
    from audit_common.errors import (
        BadRequestError,
        ConflictError,
        ForbiddenError,
        NotFoundError,
        UnauthorizedError,
    )

    assert BadRequestError().status_code == 400
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403
    assert NotFoundError().status_code == 404
    assert ConflictError().status_code == 409


def test_error_default_detail_uses_class_name():
    from audit_common.errors import NotFoundError

    err = NotFoundError()
    assert err.detail == "NotFoundError"


# ---------------------------------------------------------------- auth

def test_decode_token_fails_when_secret_unset(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from audit_common.auth import decode_token

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        decode_token("anything")


def test_decode_token_round_trip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    import jwt

    from audit_common.auth import decode_token

    tok = jwt.encode(
        {"sub": "u1", "tenant_id": "t1", "role": "admin", "email": "u@x"},
        "test-secret",
        algorithm="HS256",
    )
    user = decode_token(tok)
    assert user.user_id == "u1"
    assert user.tenant_id == "t1"
    assert user.role == "admin"
    assert user.email == "u@x"


def test_decode_token_rejects_missing_tenant_id(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    import jwt
    from fastapi import HTTPException

    from audit_common.auth import decode_token

    tok = jwt.encode({"sub": "u1"}, "test-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_token(tok)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------- logging

def test_logger_emits_json_with_request_context():
    from audit_common.logging import bind_request_context, get_logger, clear_request_context

    log = get_logger("sprint28-test")
    bind_request_context(tenant_id="tenant-x", request_id="req-42")

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    # Use the same JSON formatter the package installs.
    from audit_common.logging import _JsonFormatter

    handler.setFormatter(_JsonFormatter())
    logging.getLogger().addHandler(handler)
    try:
        log.info("hello", extra={"foo": 1})
    finally:
        logging.getLogger().removeHandler(handler)
        clear_request_context()

    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["tenant_id"] == "tenant-x"
    assert payload["request_id"] == "req-42"
    assert payload["foo"] == 1
