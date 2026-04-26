"""Sprint 22 fixtures — async Postgres connections for admin and app roles."""
from __future__ import annotations

import os
import asyncio
import asyncpg
import pytest
import pytest_asyncio


DB_ADMIN = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis",
)
DB_APP = os.getenv(
    "DATABASE_URL_APP",
    "postgresql://aegis_app:aegis_app_dev_pw@localhost:5432/aegis",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def admin_conn():
    conn = await asyncpg.connect(DB_ADMIN)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture()
async def app_conn():
    conn = await asyncpg.connect(DB_APP)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def demo_tenant() -> str:
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="session")
def other_tenant() -> str:
    return "22222222-2222-2222-2222-222222222222"
