"""End-to-end integration tests: parse → index → query."""

import pathlib

import pytest

from src.indexer.pipeline import reindex_file
from src.query.exact import find_callers, get_file_outline, get_symbol
from src.query.semantic import semantic_search

AUTH_MODULE = "tests/fixtures/auth_module.py"


async def _clean_file(pool, file_path: str) -> None:
    """Remove all indexed data for file_path from the test database."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM symbols WHERE file_path = $1", file_path)
        await conn.execute("DELETE FROM file_index WHERE file_path = $1", file_path)


async def _index_auth_module(pool) -> None:
    """Remove prior index state and run a full reindex of the auth fixture."""
    await _clean_file(pool, AUTH_MODULE)
    result = await reindex_file(AUTH_MODULE, pool)
    assert result.skipped is False
    assert result.error is None


@pytest.mark.integration
async def test_full_pipeline_indexes_fixture_file(db_pool):
    """reindex_file indexes auth_module.py with at least five symbols."""
    await _clean_file(db_pool, AUTH_MODULE)
    try:
        result = await reindex_file(AUTH_MODULE, db_pool)
        assert result.skipped is False
        assert result.symbol_count >= 5
        assert result.error is None
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_get_symbol_after_indexing(db_pool):
    """get_symbol returns validate_token metadata after indexing."""
    try:
        await _index_auth_module(db_pool)
        result = await get_symbol("validate_token", db_pool)
        assert result is not None
        assert result.name == "validate_token"
        assert result.kind == "function"
        assert result.file_path.endswith("auth_module.py")
        assert result.docstring is not None
        assert "JWT" in result.docstring
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_find_callers_after_indexing(db_pool):
    """find_callers returns a list after indexing auth_module.py."""
    try:
        await _index_auth_module(db_pool)
        result = await find_callers("validate_token", db_pool)
        assert isinstance(result, list)
        assert len(result) > 0
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_get_file_outline_returns_all_symbols(db_pool):
    """get_file_outline returns ordered symbols including class and functions."""
    try:
        await _index_auth_module(db_pool)
        symbols = await get_file_outline(AUTH_MODULE, db_pool)
        assert len(symbols) >= 5
        auth_service = next(s for s in symbols if s.name == "AuthService")
        validate = next(s for s in symbols if s.name == "validate_token")
        assert auth_service.kind == "class"
        assert validate.kind == "function"
        line_starts = [s.line_start for s in symbols]
        assert line_starts == sorted(line_starts)
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_incremental_reindex_skips_unchanged_file(db_pool):
    """Second reindex of an unchanged file is skipped and fast."""
    await _clean_file(db_pool, AUTH_MODULE)
    try:
        first = await reindex_file(AUTH_MODULE, db_pool)
        assert first.skipped is False
        second = await reindex_file(AUTH_MODULE, db_pool)
        assert second.skipped is True
        assert second.elapsed_ms < 50
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_semantic_search_finds_auth_concepts(db_pool):
    """semantic_search returns auth-related symbols after embeddings are stored."""
    try:
        await _index_auth_module(db_pool)
        results = await semantic_search("token validation and authentication", db_pool)
        assert len(results) > 0
        assert results[0].similarity > 0.4
        names = {r.name for r in results}
        assert names & {"validate_token", "authenticate", "AuthService", "revoke_token"}
    finally:
        await _clean_file(db_pool, AUTH_MODULE)


@pytest.mark.integration
async def test_reindex_removes_stale_symbols(db_pool, tmp_path):
    """Reindexing a modified file drops symbols that were removed from source."""
    modified = tmp_path / "auth_module_modified.py"
    try:
        await _index_auth_module(db_pool)
        original = pathlib.Path(AUTH_MODULE).read_text(encoding="utf-8")
        without_hash = _remove_function(original, "hash_password")
        modified.write_text(without_hash, encoding="utf-8")
        mod_path = str(modified)
        await reindex_file(mod_path, db_pool)
        symbols = await get_file_outline(mod_path, db_pool)
        names = {s.name for s in symbols}
        assert "hash_password" not in names
        assert "validate_token" in names
    finally:
        await _clean_file(db_pool, AUTH_MODULE)
        await _clean_file(db_pool, str(modified))


def _remove_function(source: str, function_name: str) -> str:
    """Return source with the named top-level function definition removed."""
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        if line.startswith(f"def {function_name}("):
            skip = True
            continue
        if skip:
            if line and not line[0].isspace() and line.strip():
                skip = False
            else:
                continue
        out.append(line)
    return "".join(out)
