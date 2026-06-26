"""Session-scoped database fixture shared across all tests."""

import os

import asyncpg
import pytest
import pytest_asyncio

from src.db import init


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool() -> asyncpg.Pool:
    """Create a pool against TEST_POSTGRES_URL, run migrations, and tear down after the session."""
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not set — skipping DB integration tests")
    pool = await asyncpg.create_pool(url)
    await init.run_migrations(pool)
    yield pool
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS relationships")
        await conn.execute("DROP TABLE IF EXISTS symbols")
        await conn.execute("DROP TABLE IF EXISTS file_index")
    await pool.close()
