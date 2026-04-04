from __future__ import annotations

import asyncpg
import structlog

from .config import settings

logger = structlog.get_logger(__name__)


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    dsn = dsn or settings.database_url
    logger.info("creating_db_pool", url=dsn[:30] + "...")
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
    )
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    logger.info("closing_db_pool")
    await pool.close()


async def execute_as_admin(pool: asyncpg.Pool, sql: str, *args) -> str:
    """
    Run a DDL or privileged DML statement outside of tenant RLS.
    Uses a dedicated connection with SET LOCAL row_security = off.
    Returns the command status string.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL row_security = off")
            result = await conn.execute(sql, *args)
    return result
