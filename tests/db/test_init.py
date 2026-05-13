"""Tests for src/db/init.py — pool creation and migration bootstrap."""

import pytest

from src.db.init import create_pool


async def test_all_tables_exist(db_pool):
    """All three schema tables are present after run_migrations."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
    names = {r["table_name"] for r in rows}
    assert "symbols" in names
    assert "relationships" in names
    assert "file_index" in names


async def test_pgvector_extension_enabled(db_pool):
    """The vector extension is installed in the database."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    assert row is not None


async def test_symbols_has_embedding_column(db_pool):
    """The symbols table exposes an embedding column for pgvector storage."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'symbols' AND column_name = 'embedding'
            """
        )
    assert row is not None


async def test_create_pool_fails_on_bad_url(monkeypatch):
    """create_pool raises when POSTGRES_URL points to an unreachable host."""
    monkeypatch.setenv("POSTGRES_URL", "postgresql://bad:bad@127.0.0.1:1/noexist")
    with pytest.raises(Exception):
        await create_pool()
