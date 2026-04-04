import asyncpg
from .config import settings

async def create_db_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=8,
        command_timeout=30,
    )
