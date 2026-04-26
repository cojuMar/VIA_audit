"""
audit_common.logging — structured JSON logging with tenant + request context.

Sprint 28 starts the migration off ad-hoc `print()` and bare `logging.getLogger`
toward a single structured log shape so downstream tooling (and Sprint 29's
observability work) can index reliably on `tenant_id` / `request_id`.

Usage from a request handler:

    log = get_logger(__name__)
    bind_request_context(tenant_id=user.tenant_id, request_id=req_id)
    log.info("fetched_engagements", extra={"count": len(rows)})
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from typing import Any

# Context vars survive across awaits but are scoped per-task.
_TENANT_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_common_tenant_id", default=None
)
_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_common_request_id", default=None
)


def bind_request_context(
    *, tenant_id: str | None = None, request_id: str | None = None
) -> None:
    """Attach tenant/request context to every subsequent log call in this task."""
    if tenant_id is not None:
        _TENANT_ID.set(tenant_id)
    if request_id is not None:
        _REQUEST_ID.set(request_id)


def clear_request_context() -> None:
    _TENANT_ID.set(None)
    _REQUEST_ID.set(None)


class _JsonFormatter(logging.Formatter):
    """One JSON object per line. Stable key order so log greps stay simple."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        tenant = _TENANT_ID.get()
        if tenant is not None:
            payload["tenant_id"] = tenant
        req = _REQUEST_ID.get()
        if req is not None:
            payload["request_id"] = req
        # `extra={...}` ends up as record attributes — surface them.
        for k, v in record.__dict__.items():
            if k in payload or k.startswith("_"):
                continue
            if k in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "taskName",
            ):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=False)


_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes structured JSON to stderr."""
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        root = logging.getLogger()
        # Don't double-handle if the host already configured logging.
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            root.addHandler(handler)
        root.setLevel(logging.INFO)
        _configured = True
    return logging.getLogger(name)
