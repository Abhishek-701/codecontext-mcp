"""End-to-end verification: index repo, exercise MCP tool handlers against real DB."""

import asyncio
import logging
import os
import pathlib
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WATCH_PATH = str(REPO_ROOT / "src")


async def _connect_urls() -> str:
    """Return the first working POSTGRES_URL from candidates."""
    candidates = [
        os.environ.get("POSTGRES_URL", ""),
        "postgresql://codecontext:codecontext@localhost:5433/codecontext",
        "postgresql://codecontext:codecontext@localhost:5432/codecontext",
        "postgresql://postgres:postgres@localhost/codecontext",
        "postgresql://postgres:postgres@localhost/postgres",
    ]
    import asyncpg

    for url in candidates:
        if not url:
            continue
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            logger.info("Connected with %s", url.split("@")[-1])
            return url
        except Exception as e:
            logger.warning("Failed %s: %s", url.split("@")[-1], e)
    raise RuntimeError("No working POSTGRES_URL found — start Docker Desktop and run: docker compose up -d")


async def _index_repo(pool) -> int:
    """Index all Python files under src/ and return symbol count."""
    from src.indexer.pipeline import reindex_file
    from src.watcher.events import is_indexable

    indexed = 0
    for path in pathlib.Path(WATCH_PATH).rglob("*.py"):
        if not is_indexable(str(path)):
            continue
        result = await reindex_file(str(path), pool)
        if not result.skipped and result.symbol_count:
            indexed += result.symbol_count
            logger.info("Indexed %s (%d symbols)", path.relative_to(REPO_ROOT), result.symbol_count)
    return indexed


async def _run_tool_checks(pool) -> None:
    """Call MCP tool handlers with a real pool and print results."""
    from src.mcp import server

    server.mcp.pool = pool

    symbol = await server.get_symbol("get_symbol", str(REPO_ROOT))
    logger.info("get_symbol: %s", "error" if "error" in symbol else symbol.get("name"))

    callers = await server.find_callers("get_symbol", str(REPO_ROOT))
    logger.info("find_callers: caller_count=%s", callers.get("caller_count"))

    history = await server.get_change_history("get_symbol", str(REPO_ROOT), limit=5)
    logger.info("get_change_history: commit_count=%s", history.get("commit_count"))

    search = await server.semantic_search("database connection pool", str(REPO_ROOT), limit=5)
    logger.info("semantic_search: result_count=%s", search.get("result_count"))
    if search.get("results"):
        top = search["results"][0]
        logger.info("  top hit: %s (similarity=%.2f)", top["name"], top["similarity"])

    outline = await server.get_file_outline(
        r"src\mcp\server.py",
        str(REPO_ROOT),
    )
    if "error" in outline:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT file_path FROM symbols WHERE name = 'get_symbol' LIMIT 1"
            )
        if row:
            outline = await server.get_file_outline(row["file_path"], str(REPO_ROOT))
    logger.info("get_file_outline: symbol_count=%s", outline.get("symbol_count"))

    errors = [k for k, v in [
        ("get_symbol", symbol),
        ("find_callers", callers),
        ("get_change_history", history),
        ("semantic_search", search),
        ("get_file_outline", outline),
    ] if "error" in v]
    if errors:
        raise RuntimeError(f"Tool errors: {errors}")
    logger.info("All five MCP tools returned data successfully")
    await _run_prompt4_demo(pool)


async def _run_prompt4_demo(pool) -> None:
    """Simulate Prompt 4: most-called symbol in mcp module + history."""
    from src.mcp import server

    server.mcp.pool = pool
    repo = str(REPO_ROOT)

    mcp_file = None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT file_path FROM symbols WHERE file_path LIKE '%mcp%server.py' LIMIT 1"
        )
        if row:
            mcp_file = row["file_path"]

    if not mcp_file:
        logger.warning("Prompt 4 demo skipped: mcp server.py not in index")
        return

    outline = await server.get_file_outline(mcp_file, repo)
    logger.info("Prompt 4 — outline: %d symbols in mcp/server.py", outline.get("symbol_count", 0))

    best_name, best_count = "", -1
    for sym in outline.get("symbols", []):
        if sym["kind"] not in ("function", "method"):
            continue
        callers = await server.find_callers(sym["name"], repo)
        count = callers.get("caller_count", 0)
        if count > best_count:
            best_count = count
            best_name = sym["name"]

    if not best_name:
        logger.warning("Prompt 4 demo: no callable symbols with callers in mcp/server.py")
        return

    definition = await server.get_symbol(best_name, repo)
    history = await server.get_change_history(best_name, repo, limit=5)
    logger.info(
        "Prompt 4 result — most-called: %s (%d callers) at %s:%s-%s",
        best_name,
        best_count,
        definition.get("file_path"),
        definition.get("line_start"),
        definition.get("line_end"),
    )
    if history.get("commits"):
        latest = history["commits"][0]
        logger.info(
            "  last change: %s by %s — %s",
            latest["hash"][:8],
            latest["author"],
            latest["message"],
        )


async def main() -> None:
    from src.db.init import create_pool, run_migrations

    url = await _connect_urls()
    os.environ["POSTGRES_URL"] = url

    pool = await create_pool()
    try:
        await run_migrations(pool)
        async with pool.acquire() as conn:
            await conn.execute("TRUNCATE relationships, symbols, file_index CASCADE")
        count = await _index_repo(pool)
        if count == 0:
            logger.warning("No symbols indexed — check WATCH_PATH and parser")
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) AS n FROM symbols")
            logger.info("Total symbols in DB: %s", row["n"])
        await _run_tool_checks(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)
