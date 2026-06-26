"""Watcher daemon: drives the poll loop that reindexes changed source files."""

import asyncio
import logging
import os
import pathlib
import sys

import asyncpg
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from src.db import queries
from src.db.init import create_pool
from src.indexer.pipeline import reindex_file
from src.watcher.debouncer import Debouncer
from src.watcher.events import FileChangeEvent
from src.watcher.handler import IndexerEventHandler

logger = logging.getLogger(__name__)


async def delete_file_index(file_path: str, pool: asyncpg.Pool) -> None:
    """Delete all indexed data for a file: removes its symbols then its file_index row.

    Relationships cascade automatically from symbols.id via the DB schema.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(queries.DELETE_SYMBOLS_FOR_FILE, file_path)
            await conn.execute(queries.DELETE_FILE_INDEX, file_path)


async def _process_event(event: FileChangeEvent, pool: asyncpg.Pool) -> None:
    """Dispatch a single drained FileChangeEvent to the appropriate handler."""
    if event.event_type == "deleted":
        await delete_file_index(event.file_path, pool)
        logger.info(
            "Removed index for deleted file",
            extra={"file": event.file_path},
        )
    else:
        result = await reindex_file(event.file_path, pool)
        logger.info(
            "Reindexed file",
            extra={
                "file": event.file_path,
                "skipped": result.skipped,
                "symbols": result.symbol_count,
                "elapsed_ms": round(result.elapsed_ms, 1),
                "error": result.error,
            },
        )


def _use_polling_observer() -> bool:
    """Return True when WATCH_USE_POLLING is set (needed for Docker bind mounts)."""
    return os.environ.get("WATCH_USE_POLLING", "").lower() in ("1", "true", "yes")


def _create_observer():
    """Return a filesystem observer; polling mode works on Docker volume mounts."""
    if _use_polling_observer():
        return PollingObserver()
    return Observer()


async def run_watcher(watch_path: str, pool: asyncpg.Pool) -> None:
    """Watch watch_path recursively and reindex source files as they change.

    Runs until KeyboardInterrupt. On each 100ms tick, drained events from
    the Debouncer are dispatched: deletions remove the index row; creations
    and modifications trigger a full reindex pipeline.
    """
    debouncer = Debouncer(delay_ms=300)
    handler = IndexerEventHandler(debouncer)

    observer = _create_observer()
    observer.schedule(handler, watch_path, recursive=True)
    observer.start()
    mode = "polling" if _use_polling_observer() else "native"
    logger.info("Watcher started", extra={"path": watch_path, "mode": mode})

    try:
        while True:
            for event in debouncer.drain():
                await _process_event(event, pool)
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Watcher stopped", extra={"path": watch_path})


async def _main(watch_path: str) -> None:
    """Create the DB pool and start the watcher loop."""
    pool = await create_pool()
    try:
        await run_watcher(watch_path, pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    watch_path = os.environ.get("WATCH_PATH", "")
    postgres_url = os.environ.get("POSTGRES_URL", "")

    if not watch_path:
        logger.error("WATCH_PATH environment variable is required")
        sys.exit(1)
    if not pathlib.Path(watch_path).exists():
        logger.error("WATCH_PATH does not exist on disk", extra={"path": watch_path})
        sys.exit(1)
    if not postgres_url:
        logger.error("POSTGRES_URL environment variable is required")
        sys.exit(1)

    asyncio.run(_main(watch_path))
