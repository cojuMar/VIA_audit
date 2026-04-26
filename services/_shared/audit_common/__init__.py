"""
audit_common — shared building blocks for every VIA backend service.

Sprint 28 introduced this package to stop the copy-paste of:
  - `tenant_conn` (was duplicated, byte-identical, in 11 services)
  - `create_pool` / `close_pool`
  - JWT validation + `get_current_user`
  - Standard HTTPException subclasses
  - Structured logging with `tenant_id` / `request_id` baked in

Every other backend service should import from here rather than re-rolling
its own `src/db.py` or `src/auth.py`.
"""
from .db import close_pool, create_pool, tenant_conn
from .errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from .logging import bind_request_context, get_logger
from .middleware import RequestContextMiddleware

__all__ = [
    "create_pool",
    "close_pool",
    "tenant_conn",
    "get_logger",
    "bind_request_context",
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ConflictError",
    "RequestContextMiddleware",
]
