"""Tests for src/db/queries.py — SQL constant correctness against the live schema."""

from src.db.queries import DELETE_SYMBOLS_FOR_FILE, GET_SYMBOL, UPSERT_FILE_INDEX


async def test_get_symbol_returns_none_when_empty(db_pool):
    """GET_SYMBOL returns None for a name that does not exist in symbols."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(GET_SYMBOL, "nonexistent_symbol_xyz_abc")
    assert row is None


async def test_upsert_file_index_inserts_and_updates(db_pool):
    """UPSERT_FILE_INDEX inserts a new row and updates it on conflict."""
    async with db_pool.acquire() as conn:
        await conn.execute(UPSERT_FILE_INDEX, "upsert_test.py", "hash_v1", 3, "python")
        row = await conn.fetchrow(
            "SELECT content_hash, symbol_count FROM file_index WHERE file_path = $1",
            "upsert_test.py",
        )
        assert row["content_hash"] == "hash_v1"
        assert row["symbol_count"] == 3

        await conn.execute(UPSERT_FILE_INDEX, "upsert_test.py", "hash_v2", 7, "python")
        row = await conn.fetchrow(
            "SELECT content_hash, symbol_count FROM file_index WHERE file_path = $1",
            "upsert_test.py",
        )
        assert row["content_hash"] == "hash_v2"
        assert row["symbol_count"] == 7

        await conn.execute("DELETE FROM file_index WHERE file_path = $1", "upsert_test.py")


async def test_delete_symbols_for_file_cascades_relationships(db_pool):
    """DELETE_SYMBOLS_FOR_FILE removes the symbol and cascades to its relationships."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO symbols
                (name, qualified_name, kind, file_path, line_start, line_end, language)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            "cascade_fn", "mod.cascade_fn", "function", "cascade_test.py", 1, 5, "python",
        )
        symbol_id = row["id"]

        await conn.execute(
            """
            INSERT INTO relationships
                (caller_id, callee_name, call_site_file, call_site_line, context_snippet)
            VALUES ($1, $2, $3, $4, $5)
            """,
            symbol_id, "other_fn", "cascade_test.py", 3, "other_fn()",
        )

        await conn.execute(DELETE_SYMBOLS_FOR_FILE, "cascade_test.py")

        rel = await conn.fetchrow(
            "SELECT id FROM relationships WHERE caller_id = $1", symbol_id
        )
        assert rel is None
