"""
audit_common.db — the canonical asyncpg pool + tenant-scoped connection helper.

Replaces the byte-identical `src/db.py` in 11 services. The tenant context is
set inside a transaction so RLS policies see `current_setting('app.tenant_id')`
for the duration of the block. The transaction is local to the `with` body —
exiting commits (or rolls back on exception); the connection is then returned
to the pool with the tenant context implicitly cleared by the transaction's end.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg


async def create_pool(
    database_url: str,
    *,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 30.0,
) -> asyncpg.Pool:
    """Build an asyncpg pool with the project's standard sizing defaults."""
    pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )
    if pool is None:
        # asyncpg returns None when called outside an event loop; surface it
        # immediately rather than letting a downstream `acquire()` confuse us.
        raise RuntimeError("asyncpg.create_pool returned None")
    return pool


async def close_pool(pool: asyncpg.Pool | None) -> None:
    """Idempotent — safe to call from a shutdown hook even if pool is None."""
    if pool is not None:
        await pool.close()


@asynccontextmanager
async def tenant_conn(
    pool: asyncpg.Pool, tenant_id: str
) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Acquire a connection with `app.tenant_id` set for the duration of the
    block. RLS policies that read `current_setting('app.tenant_id')` will see
    the supplied tenant_id and only the supplied tenant_id.

    The third argument to `set_config(..., true)` scopes the setting to the
    current transaction — so when the `async with conn.transaction()` block
    exits, the tenant context is gone too. No leakage to the next caller of
    the same pooled connection.
    """
    if not tenant_id:
        # An empty tenant_id with FORCE RLS would silently match nothing —
        # but the silent-empty-result class of bug is what we're trying to
        # avoid. Refuse explicitly.
        raise ValueError("tenant_conn requires a non-empty tenant_id")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant_id
            )
            yield conn
