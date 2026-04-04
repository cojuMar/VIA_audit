import asyncpg
from contextlib import asynccontextmanager
from src.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def tenant_conn(pool: asyncpg.Pool, tenant_id: str):
    """Async context manager that sets tenant context before yielding connection."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL app.tenant_id = $1", tenant_id
            )
            yield conn
