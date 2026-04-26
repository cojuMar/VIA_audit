"""
audit_common.middleware — FastAPI middleware that binds tenant_id +
request_id to the structured logger for the duration of every request.

Usage in a service `main.py`:

    from audit_common.middleware import RequestContextMiddleware

    app = FastAPI(...)
    app.add_middleware(RequestContextMiddleware)

After this, every `get_logger(__name__).info(...)` inside the request
automatically picks up `tenant_id` (from `X-Tenant-ID` header) and
`request_id` (from `X-Request-ID`, or a freshly generated UUID).

The acceptance criterion for Sprint 29 is "tenant_id + request_id on every
log line"; this middleware is the mechanism.
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging import bind_request_context, clear_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind tenant_id / request_id into the log context for one request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Trust the client-supplied request id if it looks like a uuid; else
        # mint our own. We deliberately don't trust arbitrary strings here
        # because they end up in log indices.
        incoming = request.headers.get("X-Request-ID")
        try:
            request_id = str(uuid.UUID(incoming)) if incoming else str(uuid.uuid4())
        except (ValueError, AttributeError):
            request_id = str(uuid.uuid4())

        tenant_id = request.headers.get("X-Tenant-ID") or None

        bind_request_context(tenant_id=tenant_id, request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        # Echo the request id back so a client can correlate logs to a call.
        response.headers["X-Request-ID"] = request_id
        return response
