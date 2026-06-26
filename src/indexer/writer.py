"""Writes parsed symbols and call sites to the database inside a single transaction."""

import hashlib
import logging
import pathlib
from typing import Optional

import asyncpg

from src.db.queries import (
    DELETE_SYMBOLS_FOR_FILE,
    GET_SYMBOL_BY_ID,
    INSERT_RELATIONSHIP,
    INSERT_SYMBOL,
    RESOLVE_CALLEE_ID,
    UPDATE_SYMBOL_EMBEDDING,
    UPSERT_FILE_INDEX,
)
from src.indexer.models import CallSite, Symbol

logger = logging.getLogger(__name__)


def _compute_hash(file_path: str) -> str:
    """Return the SHA-256 hex digest of the file at file_path."""
    return hashlib.sha256(pathlib.Path(file_path).read_bytes()).hexdigest()


async def _insert_symbols(
    conn: asyncpg.Connection, symbols: list[Symbol]
) -> dict[str, int]:
    """Insert symbols into the DB and return a mapping of name → new id."""
    name_to_id: dict[str, int] = {}
    for sym in symbols:
        row = await conn.fetchrow(
            INSERT_SYMBOL,
            sym.name, sym.qualified_name, sym.kind, sym.file_path,
            sym.line_start, sym.line_end, sym.docstring, sym.language,
        )
        name_to_id[sym.name] = row["id"]
    return name_to_id


async def _insert_call_sites(
    conn: asyncpg.Connection,
    call_sites: list[CallSite],
    name_to_id: dict[str, int],
) -> None:
    """Insert relationship rows, resolving callee_id where possible."""
    for cs in call_sites:
        caller_id: Optional[int] = name_to_id.get(cs.caller_name)
        if caller_id is None:
            continue
        callee_row = await conn.fetchrow(RESOLVE_CALLEE_ID, cs.callee_name)
        callee_id: Optional[int] = callee_row["id"] if callee_row else None
        await conn.execute(
            INSERT_RELATIONSHIP,
            caller_id, cs.callee_name, callee_id,
            cs.call_site_file, cs.call_site_line, cs.context_snippet,
        )


async def write_symbols(
    symbols: list[Symbol],
    call_sites: list[CallSite],
    file_path: str,
    language: str,
    pool: asyncpg.Pool,
) -> int:
    """Write symbols and relationships for one file in a single atomic transaction.

    Returns the number of symbols written.
    """
    content_hash = _compute_hash(file_path)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(DELETE_SYMBOLS_FOR_FILE, file_path)
            name_to_id = await _insert_symbols(conn, symbols)
            await _insert_call_sites(conn, call_sites, name_to_id)
            await conn.execute(
                UPSERT_FILE_INDEX, file_path, content_hash, len(symbols), language
            )
    return len(symbols)


async def generate_and_store_embeddings(
    symbol_ids: list[int],
    pool: asyncpg.Pool,
) -> None:
    """Generate and store embeddings for a list of symbol ids (best-effort, not transactional)."""
    from src.query.semantic import generate_embedding  # lazy: module may not exist yet

    async with pool.acquire() as conn:
        for sym_id in symbol_ids:
            try:
                row = await conn.fetchrow(GET_SYMBOL_BY_ID, sym_id)
                if row is None:
                    continue
                text: str = row["docstring"] or row["name"]
                embedding = generate_embedding(text)
                vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await conn.execute(UPDATE_SYMBOL_EMBEDDING, vec_str, sym_id)
            except Exception as e:
                logger.warning(
                    "Embedding generation failed",
                    extra={"symbol_id": sym_id, "error": str(e)},
                )
