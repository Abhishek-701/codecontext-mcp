"""Tests for src/query/semantic.py: generate_embedding and semantic_search.

Ordering matters for the DB tests: the "no embeddings" test must run before
any symbols with embeddings are committed, so it is placed first among the
db_pool tests. Each DB test cleans up in a finally block.
"""

import asyncpg

from src.db.queries import INSERT_SYMBOL, UPDATE_SYMBOL_EMBEDDING
from src.query.semantic import generate_embedding, semantic_search


async def insert_symbol(pool: asyncpg.Pool, **kwargs) -> int:
    """Insert a symbol row using INSERT_SYMBOL and return its generated id."""
    defaults = dict(
        name="sem_test_sym",
        qualified_name="tests.query.sem_test_sym",
        kind="function",
        file_path="tests/query/semantic/placeholder.py",
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
    """Delete all symbols for file_path (cascades to relationships)."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM symbols WHERE file_path = $1", file_path)


def test_generate_embedding_returns_list_of_floats():
    """generate_embedding returns a list[float] of length 384 for all-MiniLM-L6-v2."""
    result = generate_embedding("validate authentication token")
    assert isinstance(result, list)
    assert len(result) == 384
    assert all(isinstance(x, float) for x in result)


def test_generate_embedding_is_deterministic():
    """generate_embedding returns identical vectors on repeated calls for the same input."""
    text = "same text deterministic check"
    assert generate_embedding(text) == generate_embedding(text)


async def test_semantic_search_returns_empty_when_no_embeddings(db_pool):
    """semantic_search returns [] when no symbols in the DB have non-null embeddings.

    Placed before test_semantic_search_returns_results so the DB contains no
    embeddings at the time this test runs.
    """
    fp = "tests/query/semantic/no_embed.py"
    await insert_symbol(
        db_pool,
        name="sem_no_embed_fn",
        qualified_name="tests.sem_no_embed_fn",
        kind="function",
        file_path=fp,
        docstring="This symbol intentionally has no embedding stored.",
    )
    try:
        results = await semantic_search("anything", db_pool, limit=10)
        assert results == []
    finally:
        await _clean(db_pool, fp)


async def test_semantic_search_returns_results(db_pool):
    """semantic_search returns at least one result with similarity > 0 after storing embeddings."""
    fp = "tests/query/semantic/with_embed.py"
    symbols = [
        ("sem_auth_handler", "Handles authentication errors and returns 401 responses."),
        ("sem_token_validator", "Validates JWT tokens and checks token expiry."),
        ("sem_login_endpoint", "Processes user login requests and issues session tokens."),
    ]
    ids_and_docs: list[tuple[int, str]] = []
    for name, docstring in symbols:
        sym_id = await insert_symbol(
            db_pool,
            name=name,
            qualified_name=f"tests.{name}",
            kind="function",
            file_path=fp,
            docstring=docstring,
        )
        ids_and_docs.append((sym_id, docstring))
    try:
        async with db_pool.acquire() as conn:
            for sym_id, docstring in ids_and_docs:
                embedding = generate_embedding(docstring)
                vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await conn.execute(UPDATE_SYMBOL_EMBEDDING, vec_str, sym_id)
        results = await semantic_search("authentication", db_pool, limit=3)
        assert len(results) >= 1
        assert all(r.similarity > 0 for r in results)
    finally:
        await _clean(db_pool, fp)
