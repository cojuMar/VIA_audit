import asyncpg
from .config import settings


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)


async def close_pool(pool: asyncpg.Pool):
    await pool.close()
