"""Integration tests for src/query/exact.py."""

import asyncpg

from src.db.queries import INSERT_RELATIONSHIP, INSERT_SYMBOL
from src.query.exact import (
    find_callers,
    get_change_history,
    get_file_outline,
    get_symbol,
)


async def insert_symbol(pool: asyncpg.Pool, **kwargs) -> int:
    """Insert a symbol row using INSERT_SYMBOL and return its generated id."""
    defaults = dict(
        name="exact_test_sym",
        qualified_name="tests.query.exact_test_sym",
        kind="function",
        file_path="tests/query/exact/placeholder.py",
        line_start=1,
        line_end=10,
        docstring=None,
        language="python",
    )
    defaults.update(kwargs)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            INSERT_SYMBOL,
            defaults["name"], defaults["qualified_name"], defaults["kind"],
            defaults["file_path"], defaults["line_start"], defaults["line_end"],
            defaults["docstring"], defaults["language"],
        )
    return row["id"]


async def _clean(pool: asyncpg.Pool, file_path: str) -> None:
    """Delete all symbols (and cascaded relationships) for a given file_path."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM symbols WHERE file_path = $1", file_path)


async def test_get_symbol_returns_correct_fields(db_pool):
    """get_symbol returns a Symbol whose fields match the inserted row."""
    fp = "tests/query/exact/test_get_symbol.py"
    await insert_symbol(
        db_pool,
        name="get_symbol_validate_token",
        qualified_name="auth.validator.get_symbol_validate_token",
        kind="function",
        file_path=fp,
        line_start=10,
        line_end=20,
    )
    try:
        result = await get_symbol("get_symbol_validate_token", db_pool)
        assert result is not None
        assert result.name == "get_symbol_validate_token"
        assert result.kind == "function"
        assert result.file_path == fp
        assert result.line_start == 10
        assert result.line_end == 20
    finally:
        await _clean(db_pool, fp)


async def test_get_symbol_returns_none_for_missing(db_pool):
    """get_symbol returns None when the name does not exist in the index."""
    result = await get_symbol("nonexistent_xyz_exact_999", db_pool)
    assert result is None


async def test_find_callers_returns_call_sites(db_pool):
    """find_callers returns a CallSite with correct caller_name and call_site_line."""
    fp = "tests/query/exact/test_find_callers.py"
    caller_id = await insert_symbol(
        db_pool,
        name="find_callers_caller_fn",
        qualified_name="tests.find_callers_caller_fn",
        kind="function",
        file_path=fp,
        line_start=1,
        line_end=5,
    )
    callee_id = await insert_symbol(
        db_pool,
        name="find_callers_callee_fn",
        qualified_name="tests.find_callers_callee_fn",
        kind="function",
        file_path=fp,
        line_start=10,
        line_end=15,
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            INSERT_RELATIONSHIP,
            caller_id, "find_callers_callee_fn", callee_id,
            fp, 42, "find_callers_callee_fn()",
        )
    try:
        results = await find_callers("find_callers_callee_fn", db_pool)
        assert len(results) == 1
        cs = results[0]
        assert cs.caller_name == "find_callers_caller_fn"
        assert cs.call_site_line == 42
    finally:
        await _clean(db_pool, fp)


async def test_find_callers_returns_empty_list_for_no_callers(db_pool):
    """find_callers returns [] for a symbol with no relationship rows — not an error."""
    fp = "tests/query/exact/test_find_callers_empty.py"
    await insert_symbol(
        db_pool,
        name="find_callers_lonely_fn",
        qualified_name="tests.find_callers_lonely_fn",
        kind="function",
        file_path=fp,
    )
    try:
        results = await find_callers("find_callers_lonely_fn", db_pool)
        assert results == []
    finally:
        await _clean(db_pool, fp)


async def test_get_file_outline_returns_symbols_in_line_order(db_pool):
    """get_file_outline returns all file symbols sorted ascending by line_start."""
    fp = "tests/query/exact/test_outline.py"
    for name, line_start in [
        ("outline_fn_c", 50),
        ("outline_fn_a", 10),
        ("outline_fn_b", 30),
    ]:
        await insert_symbol(
            db_pool,
            name=name,
            qualified_name=f"tests.{name}",
            kind="function",
            file_path=fp,
            line_start=line_start,
            line_end=line_start + 5,
        )
    try:
        symbols = await get_file_outline(fp, db_pool)
        assert len(symbols) == 3
        assert [s.line_start for s in symbols] == [10, 30, 50]
    finally:
        await _clean(db_pool, fp)


async def test_get_change_history_returns_empty_for_missing_symbol(db_pool):
    """get_change_history returns [] without raising when the symbol is not indexed."""
    result = await get_change_history("nonexistent_xyz_exact_999", "/tmp", db_pool)
    assert result == []


async def test_get_change_history_returns_empty_for_non_git_path(db_pool):
    """get_change_history returns [] when repo_path is not a git repository."""
    fp = "tests/query/exact/test_git_history.py"
    await insert_symbol(
        db_pool,
        name="git_history_test_sym",
        qualified_name="tests.git_history_test_sym",
        kind="function",
        file_path=fp,
        line_start=1,
        line_end=10,
    )
    try:
        result = await get_change_history("git_history_test_sym", "/tmp", db_pool)
        assert result == []
    finally:
        await _clean(db_pool, fp)
