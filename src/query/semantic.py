"""Semantic search using pgvector embeddings and sentence-transformers."""

import logging
import os
import threading

import asyncpg
from sentence_transformers import SentenceTransformer

from src.db import queries
from src.query.models import SearchResult

logger = logging.getLogger(__name__)

# Loaded lazily on first call to generate_embedding or semantic_search.
_MODEL = None
_MODEL_LOCK = threading.Lock()


def _get_model() -> SentenceTransformer:
    """Return the sentence-transformers model, loading it once on first call.

    Uses double-checked locking so concurrent callers do not race to load
    the model more than once.
    """
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
                logger.info("Loading embedding model", extra={"model": model_name})
                _MODEL = SentenceTransformer(model_name)
    return _MODEL


def generate_embedding(text: str) -> list[float]:
    """Return the embedding vector for text as a plain Python float list.

    Logs ERROR and re-raises on model load failure or encode error so that
    callers can decide whether to swallow the exception.
    """
    try:
        return _get_model().encode(text).tolist()
    except Exception as e:
        logger.error(
            "Embedding generation failed",
            extra={"text_len": len(text), "error": str(e)},
        )
        raise


async def semantic_search(
    query: str,
    pool: asyncpg.Pool,
    limit: int = 10,
) -> list[SearchResult]:
    """Return symbols whose meaning best matches query, ranked by cosine similarity.

    Returns an empty list if the embedding model is unavailable or if no
    symbols with embeddings exist. Never raises.
    """
    try:
        embedding = generate_embedding(query)
    except Exception as e:
        logger.error(
            "semantic_search aborted: embedding unavailable",
            extra={"query": query, "error": str(e)},
        )
        return []

    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch(queries.SEMANTIC_SEARCH, vec_str, limit)

    return [
        SearchResult(
            name=row["name"],
            qualified_name=row["qualified_name"],
            kind=row["kind"],
            file_path=row["file_path"],
            line_start=row["line_start"],
            docstring=row["docstring"],
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]
