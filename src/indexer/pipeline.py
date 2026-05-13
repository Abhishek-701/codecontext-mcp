"""Full reindex pipeline: hash check → parse → write → embed."""

import hashlib
import logging
import pathlib
import time

import asyncpg

from src.db.queries import GET_FILE_HASH, GET_SYMBOL_IDS_FOR_FILE
from src.indexer.models import IndexResult
from src.indexer.parser import parse_file
from src.indexer.writer import generate_and_store_embeddings, write_symbols

logger = logging.getLogger(__name__)


async def reindex_file(file_path: str, pool: asyncpg.Pool) -> IndexResult:
    """Run the full index pipeline for one file; never raises — errors are returned in IndexResult."""
    start = time.monotonic()
    try:
        content = pathlib.Path(file_path).read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(GET_FILE_HASH, file_path)
        if row and row["content_hash"] == content_hash:
            return IndexResult(
                file_path=file_path, skipped=True,
                symbol_count=0, elapsed_ms=0.0, error=None,
            )

        symbols, call_sites = parse_file(file_path)
        language = symbols[0].language if symbols else "unknown"

        symbol_count = await write_symbols(
            symbols, call_sites, file_path, language, pool
        )

        async with pool.acquire() as conn:
            id_rows = await conn.fetch(GET_SYMBOL_IDS_FOR_FILE, file_path)
        await generate_and_store_embeddings([r["id"] for r in id_rows], pool)

        elapsed_ms = (time.monotonic() - start) * 1000
        return IndexResult(
            file_path=file_path, skipped=False,
            symbol_count=symbol_count, elapsed_ms=elapsed_ms, error=None,
        )
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error("Reindex failed", extra={"file": file_path, "error": str(e)})
        return IndexResult(
            file_path=file_path, skipped=False,
            symbol_count=0, elapsed_ms=elapsed_ms, error=str(e),
        )
