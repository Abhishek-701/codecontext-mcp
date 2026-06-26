"""One-shot full-tree index for cold start (e.g. Docker bootstrap service)."""

import asyncio
import logging
import os
import pathlib
import sys

from src.db.init import create_pool
from src.indexer.pipeline import reindex_file
from src.watcher.events import is_indexable

logger = logging.getLogger(__name__)


async def index_tree(watch_path: str, pool) -> int:
    """Index every indexable source file under watch_path and return total symbol count."""
    total = 0
    root = pathlib.Path(watch_path)
    for path in root.rglob("*"):
        if not path.is_file() or not is_indexable(str(path)):
            continue
        result = await reindex_file(str(path), pool)
        if result.error:
            logger.error(
                "Bootstrap index failed",
                extra={"file": str(path), "error": result.error},
            )
            continue
        total += result.symbol_count
        logger.info(
            "Indexed file",
            extra={"file": str(path), "symbols": result.symbol_count},
        )
    return total


async def _main(watch_path: str) -> None:
    """Create a DB pool, index the tree, and exit."""
    pool = await create_pool()
    try:
        count = await index_tree(watch_path, pool)
        logger.info("Bootstrap complete", extra={"symbol_count": count})
    finally:
        await pool.close()


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    watch_path = os.environ.get("WATCH_PATH", "")
    if not watch_path:
        logger.error("WATCH_PATH environment variable is required")
        sys.exit(1)
    if not pathlib.Path(watch_path).exists():
        logger.error("WATCH_PATH does not exist on disk", extra={"path": watch_path})
        sys.exit(1)
    if not os.environ.get("POSTGRES_URL", ""):
        logger.error("POSTGRES_URL environment variable is required")
        sys.exit(1)

    asyncio.run(_main(watch_path))
