"""Structured queries against the symbols and relationships tables."""

import logging
import re
import subprocess

import asyncpg

from src.db import queries
from src.indexer.models import Symbol
from src.query.models import CallSite, Commit, FileSymbol

logger = logging.getLogger(__name__)

# Matches the 40-char hex hash at the start of a git log format line.
_COMMIT_HEADER_RE = re.compile(r"^[0-9a-f]{40}\|")


def _parse_git_log(stdout: str, limit: int) -> list[Commit]:
    """Parse interleaved git log -L output (commit headers + diffs) into Commits.

    Commit header lines match the format '%H|%an|%aI|%s'. Diff lines that
    follow each header are scanned to count added and removed lines.
    """
    commits: list[Commit] = []
    current_parts: list[str] | None = None
    diff_count = 0

    for line in stdout.splitlines():
        if _COMMIT_HEADER_RE.match(line):
            if current_parts is not None:
                commits.append(Commit(
                    hash=current_parts[0],
                    author=current_parts[1],
                    date=current_parts[2],
                    message=current_parts[3],
                    lines_changed=diff_count,
                ))
            current_parts = line.split("|", 3)
            diff_count = 0
        elif current_parts is not None:
            is_addition = line.startswith("+") and not line.startswith("+++")
            is_deletion = line.startswith("-") and not line.startswith("---")
            if is_addition or is_deletion:
                diff_count += 1

    if current_parts is not None:
        commits.append(Commit(
            hash=current_parts[0],
            author=current_parts[1],
            date=current_parts[2],
            message=current_parts[3],
            lines_changed=diff_count,
        ))

    return commits[:limit]


async def get_symbol(name: str, pool: asyncpg.Pool) -> Symbol | None:
    """Return the Symbol for the given name, or None if not found.

    Maps the DB row manually because GET_SYMBOL includes indexed_at,
    which is not a field on the Symbol dataclass.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(queries.GET_SYMBOL, name)
    if row is None:
        return None
    return Symbol(
        id=row["id"],
        name=row["name"],
        qualified_name=row["qualified_name"],
        kind=row["kind"],
        file_path=row["file_path"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        docstring=row["docstring"],
        language=row["language"],
    )


async def find_callers(symbol_name: str, pool: asyncpg.Pool) -> list[CallSite]:
    """Return all CallSites where symbol_name is invoked.

    Returns an empty list when no callers exist — not an error.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(queries.FIND_CALLERS, symbol_name)
    return [
        CallSite(
            caller_name=row["caller_name"],
            caller_file=row["caller_file"],
            call_site_file=row["call_site_file"],
            call_site_line=row["call_site_line"],
            context_snippet=row["context_snippet"],
        )
        for row in rows
    ]


async def get_file_outline(file_path: str, pool: asyncpg.Pool) -> list[FileSymbol]:
    """Return all indexed symbols in file_path, ordered by line_start.

    Returns an empty list when the file has no indexed symbols.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(queries.GET_FILE_OUTLINE, file_path)
    return [
        FileSymbol(
            name=row["name"],
            kind=row["kind"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            docstring=row["docstring"],
        )
        for row in rows
    ]


async def get_change_history(
    symbol_name: str,
    repo_path: str,
    pool: asyncpg.Pool,
    limit: int = 10,
) -> list[Commit]:
    """Return git commits that touched the lines of symbol_name.

    Queries the DB for the symbol's file and line range, then runs
    git log -L to retrieve the relevant commit history. Returns []
    if the symbol is not found or git fails — callers treat an empty
    list as "no history available".
    """
    symbol = await get_symbol(symbol_name, pool)
    if symbol is None:
        logger.warning(
            "Symbol not found for history lookup",
            extra={"symbol": symbol_name},
        )
        return []

    cmd = [
        "git", "log",
        "--format=%H|%an|%aI|%s",
        "--follow",
        f"-L{symbol.line_start},{symbol.line_end}:{symbol.file_path}",
        f"-n{limit}",
    ]
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "git log failed",
            extra={"symbol": symbol_name, "stderr": result.stderr.strip()},
        )
        return []

    return _parse_git_log(result.stdout, limit)
