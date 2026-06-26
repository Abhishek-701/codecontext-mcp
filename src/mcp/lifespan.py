"""Startup and shutdown lifecycle for the CodeContext MCP server."""

import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from src.query import create_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(server):
    """Create the DB pool on startup and close it cleanly on shutdown."""
    postgres_url = os.environ.get("POSTGRES_URL", "")
    if not postgres_url:
        logger.error("POSTGRES_URL environment variable is required")
        raise RuntimeError("POSTGRES_URL is not set")

    server.pool = await create_pool()
    host = urlparse(postgres_url).hostname or "unknown"
    logger.info("CodeContext MCP server started")
    logger.info(f"Watching index at {host}")

    try:
        yield
    finally:
        await server.pool.close()
        logger.info("CodeContext MCP server stopped")
