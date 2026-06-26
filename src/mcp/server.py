"""CodeContext MCP server — five tools over the query engine."""

import dataclasses

from fastmcp import FastMCP

from src.mcp.lifespan import app_lifespan
from src.query import exact as query_exact
from src.query import semantic as query_semantic

mcp = FastMCP("codecontext", lifespan=app_lifespan)


@mcp.tool()
async def get_symbol(name: str, repo_path: str) -> dict:
    """Return definition, location and docstring for a named symbol."""
    if not name.strip() or not repo_path.strip():
        return {"error": "name and repo_path are required", "code": "INVALID_INPUT"}
    result = await query_exact.get_symbol(name, mcp.pool)
    if result is None:
        return {"error": f"Symbol '{name}' not found", "code": "SYMBOL_NOT_FOUND"}
    return dataclasses.asdict(result)


@mcp.tool()
async def find_callers(symbol_name: str, repo_path: str) -> dict:
    """Return all call sites of a named symbol across the repo."""
    if not symbol_name.strip() or not repo_path.strip():
        return {"error": "symbol_name and repo_path are required", "code": "INVALID_INPUT"}
    callers = await query_exact.find_callers(symbol_name, mcp.pool)
    return {
        "symbol_name": symbol_name,
        "caller_count": len(callers),
        "callers": [dataclasses.asdict(c) for c in callers],
    }


@mcp.tool()
async def get_change_history(
    symbol_name: str,
    repo_path: str,
    limit: int = 10,
) -> dict:
    """Return git commit history for lines touched by a symbol."""
    if not symbol_name.strip() or not repo_path.strip():
        return {"error": "symbol_name and repo_path are required", "code": "INVALID_INPUT"}
    limit = max(1, min(limit, 50))
    commits = await query_exact.get_change_history(symbol_name, repo_path, mcp.pool, limit)
    return {
        "symbol_name": symbol_name,
        "commit_count": len(commits),
        "commits": [dataclasses.asdict(c) for c in commits],
    }


@mcp.tool()
async def semantic_search(
    query_text: str,
    repo_path: str,
    limit: int = 10,
) -> dict:
    """Find symbols whose meaning matches a natural language query."""
    if not query_text.strip() or not repo_path.strip():
        return {"error": "query_text and repo_path are required", "code": "INVALID_INPUT"}
    limit = max(1, min(limit, 50))
    results = await query_semantic.semantic_search(query_text, mcp.pool, limit)
    return {
        "query": query_text,
        "result_count": len(results),
        "results": [dataclasses.asdict(r) for r in results],
    }


@mcp.tool()
async def get_file_outline(file_path: str, repo_path: str) -> dict:
    """Return all top-level symbols in a file in line order."""
    if not file_path.strip() or not repo_path.strip():
        return {"error": "file_path and repo_path are required", "code": "INVALID_INPUT"}
    symbols = await query_exact.get_file_outline(file_path, mcp.pool)
    if not symbols:
        return {
            "error": f"File '{file_path}' has not been indexed",
            "code": "FILE_NOT_INDEXED",
        }
    return {
        "file_path": file_path,
        "symbol_count": len(symbols),
        "symbols": [dataclasses.asdict(s) for s in symbols],
    }


if __name__ == "__main__":
    mcp.run()
