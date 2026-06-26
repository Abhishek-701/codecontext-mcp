"""Tests for one-shot bootstrap indexing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.indexer.bootstrap import index_tree
from src.indexer.models import IndexResult


@pytest.mark.asyncio
async def test_index_tree_skips_non_indexable_files(tmp_path, monkeypatch):
    """index_tree only calls reindex_file for indexable source files."""
    (tmp_path / "skip.txt").write_text("nope", encoding="utf-8")
    py_file = tmp_path / "module.py"
    py_file.write_text("def foo():\n    pass\n", encoding="utf-8")

    mock_reindex = AsyncMock(
        return_value=IndexResult(
            file_path=str(py_file),
            skipped=False,
            symbol_count=1,
            elapsed_ms=1.0,
            error=None,
        )
    )
    monkeypatch.setattr("src.indexer.bootstrap.reindex_file", mock_reindex)

    pool = MagicMock()
    total = await index_tree(str(tmp_path), pool)

    assert total == 1
    mock_reindex.assert_awaited_once_with(str(py_file), pool)
