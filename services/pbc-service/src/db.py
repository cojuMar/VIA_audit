"""
pbc-service db helpers.

Sprint 28 replaced the byte-identical `tenant_conn` / `create_pool` impls
that lived here with a re-export from `audit_common`. The public surface
(`create_pool`, `close_pool`, `tenant_conn`) is unchanged so call sites
don't need to be touched.
"""
from __future__ import annotations

from audit_common.db import close_pool, tenant_conn
from audit_common.db import create_pool as _create_pool

from .config import settings


async def create_pool():  # noqa: D401 — thin shim that injects settings
    """Build the asyncpg pool with this service's `database_url`."""
    return await _create_pool(settings.database_url, min_size=2, max_size=10)


__all__ = ["create_pool", "close_pool", "tenant_conn"]
