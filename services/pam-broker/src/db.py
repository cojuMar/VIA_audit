from __future__ import annotations

import asyncpg
import structlog

from .config import settings

logger = structlog.get_logger(__name__)


async def create_pool() -> asyncpg.Pool:
    logger.info("creating_db_pool", url=settings.database_url[:30] + "...")
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
    )
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    logger.info("closing_db_pool")
    await pool.close()
