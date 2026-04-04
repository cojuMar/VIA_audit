from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised")
    return _pool


def set_pool(p: asyncpg.Pool) -> None:
    global _pool
    _pool = p


async def init_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    set_pool(pool)
    return pool


@asynccontextmanager
async def tenant_conn(
    pool: asyncpg.Pool, tenant_id: str
) -> AsyncGenerator[asyncpg.Connection, None]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            yield conn
