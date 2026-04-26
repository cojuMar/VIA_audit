"""
audit_common.errors — standard HTTPException subclasses for every service.

Each subclass freezes the status code so callers don't repeat the integer
literal at every raise site, and so a global handler can dispatch on type
rather than `status_code == 404`.

These are import-light: FastAPI is the only dependency. Services that don't
use FastAPI (workers, CLIs) can ignore this module.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class _StatusError(HTTPException):
    """Internal — sets the status_code class attribute on subclasses."""

    status_code: int = 500

    def __init__(self, detail: Any = None, headers: dict[str, str] | None = None):
        super().__init__(
            status_code=self.status_code,
            detail=detail or self.__class__.__name__,
            headers=headers,
        )


class BadRequestError(_StatusError):
    """400 — caller sent invalid input. Detail should describe the field."""

    status_code = 400


class UnauthorizedError(_StatusError):
    """401 — missing or invalid credentials."""

    status_code = 401


class ForbiddenError(_StatusError):
    """403 — authenticated but not allowed (e.g. wrong tenant, wrong role)."""

    status_code = 403


class NotFoundError(_StatusError):
    """404 — resource doesn't exist (or RLS hides it from the caller)."""

    status_code = 404


class ConflictError(_StatusError):
    """409 — uniqueness, version, or business-rule conflict."""

    status_code = 409
