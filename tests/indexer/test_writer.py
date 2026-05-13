"""Integration tests for src/indexer/writer.py and src/indexer/pipeline.py."""

import pathlib

import pytest

import src.indexer.writer as writer_mod
from src.indexer.models import Symbol
from src.indexer.pipeline import reindex_file
from src.indexer.writer import write_symbols

FIXTURE = str(pathlib.Path(__file__).parent.parent / "fixtures" / "simple_functions.py")


async def _clean(pool, file_path: str) -> None:
    """Delete all test rows for file_path from symbols and file_index."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM symbols WHERE file_path = $1", file_path)
        await conn.execute("DELETE FROM file_index WHERE file_path = $1", file_path)


def _sym(name: str, file_path: str = FIXTURE) -> Symbol:
    """Build a minimal Symbol for use in writer tests."""
    return Symbol(
        id=None, name=name,
        qualified_name=f"tests.fixtures.{name}",
        kind="function", file_path=file_path,
        line_start=1, line_end=5,
        docstring=None, language="python",
    )


async def test_write_symbols_inserts_rows(db_pool):
    """write_symbols inserts every symbol and returns the correct count."""
    await _clean(db_pool, FIXTURE)
    try:
        symbols = [_sym("writer_fn_alpha"), _sym("writer_fn_beta")]
        count = await write_symbols(symbols, [], FIXTURE, "python", db_pool)
        assert count == 2
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name FROM symbols WHERE file_path = $1", FIXTURE
            )
        names = {r["name"] for r in rows}
        assert "writer_fn_alpha" in names
        assert "writer_fn_beta" in names
    finally:
        await _clean(db_pool, FIXTURE)


async def test_write_symbols_skips_unchanged_file(db_pool):
    """reindex_file returns skipped=True on the second call when the file is unchanged."""
    await _clean(db_pool, FIXTURE)
    try:
        await reindex_file(FIXTURE, db_pool)
        result = await reindex_file(FIXTURE, db_pool)
        assert result.skipped is True
    finally:
        await _clean(db_pool, FIXTURE)


async def test_write_symbols_cleans_up_on_reindex(db_pool):
    """A second write_symbols call for the same file replaces — not appends — symbols."""
    await _clean(db_pool, FIXTURE)
    try:
        await write_symbols([_sym("stale_symbol")], [], FIXTURE, "python", db_pool)
        await write_symbols([_sym("fresh_symbol")], [], FIXTURE, "python", db_pool)
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name FROM symbols WHERE file_path = $1", FIXTURE
            )
        names = {r["name"] for r in rows}
        assert "fresh_symbol" in names
        assert "stale_symbol" not in names
    finally:
        await _clean(db_pool, FIXTURE)


async def test_transaction_rolls_back_on_error(db_pool, monkeypatch):
    """A failure during INSERT rolls back the entire transaction, restoring prior symbols."""
    await _clean(db_pool, FIXTURE)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO symbols
                (name, qualified_name, kind, file_path, line_start, line_end, language)
            VALUES ('pre_existing', 'pre_existing', 'function', $1, 1, 5, 'python')
            """,
            FIXTURE,
        )

    async def _fail(conn, symbols):
        raise RuntimeError("Simulated insert failure")

    monkeypatch.setattr(writer_mod, "_insert_symbols", _fail)
    try:
        with pytest.raises(RuntimeError):
            await write_symbols([_sym("should_not_appear")], [], FIXTURE, "python", db_pool)
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name FROM symbols WHERE file_path = $1", FIXTURE
            )
        names = {r["name"] for r in rows}
        assert "pre_existing" in names
        assert "should_not_appear" not in names
    finally:
        await _clean(db_pool, FIXTURE)
