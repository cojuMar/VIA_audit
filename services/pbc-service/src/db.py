from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from .config import settings


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()


@asynccontextmanager
async def tenant_conn(
    pool: asyncpg.Pool, tenant_id: str
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection with tenant RLS context set for the duration of the block."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn
