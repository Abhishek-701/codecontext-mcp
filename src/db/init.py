"""Database pool creation and schema migration utilities."""

import logging
import os
import pathlib

import asyncpg

logger = logging.getLogger(__name__)

_SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool using POSTGRES_URL from the environment."""
    url = os.environ["POSTGRES_URL"]
    pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
    logger.info("Database connection pool created")
    return pool


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Enable pgvector and apply schema.sql, safe to call on every startup."""
    async with pool.acquire() as conn:
        logger.info("Enabling pgvector extension")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        schema_sql = _SCHEMA_PATH.read_text()
        logger.info("Applying schema migrations", extra={"schema_file": str(_SCHEMA_PATH)})
        await conn.execute(schema_sql)

    logger.info("Migrations complete")


async def _main() -> None:
    """Create pool, run migrations, then close — used as the CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pool = await create_pool()
    try:
        await run_migrations(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
