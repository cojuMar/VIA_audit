from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=20)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised")
    return _pool


@asynccontextmanager
async def tenant_conn(
    pool: asyncpg.Pool, tenant_id: str
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection and set the Row-Level Security tenant context."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn
