"""Unit tests for src/watcher/handler.py — IndexerEventHandler filtering."""

import time
from unittest.mock import MagicMock

from src.watcher.debouncer import Debouncer
from src.watcher.events import FileChangeEvent
from src.watcher.handler import IndexerEventHandler


def _mock_fs_event(src_path: str, is_directory: bool = False) -> MagicMock:
    """Build a minimal mock watchdog filesystem event."""
    event = MagicMock()
    event.src_path = src_path
    event.is_directory = is_directory
    return event


def test_handler_adds_event_to_debouncer_on_modify():
    """A modification to a supported file must be enqueued in the debouncer."""
    debouncer = Debouncer(delay_ms=300)
    handler = IndexerEventHandler(debouncer)
    file_path = "src/auth/validator.py"

    handler.on_modified(_mock_fs_event(file_path))

    # Back-date the pending event so it clears the delay window on drain.
    debouncer._pending[file_path] = FileChangeEvent(
        file_path=file_path,
        event_type="modified",
        timestamp=time.monotonic() - 0.4,
    )
    result = debouncer.drain()
    assert len(result) == 1
    assert result[0].event_type == "modified"


def test_handler_ignores_directory_events():
    """Directory events must be dropped before reaching the debouncer."""
    debouncer = Debouncer(delay_ms=300)
    handler = IndexerEventHandler(debouncer)

    handler.on_modified(_mock_fs_event("src/auth/", is_directory=True))

    assert debouncer.drain() == []


def test_handler_ignores_unsupported_extensions():
    """Events for files with unsupported extensions must be dropped silently."""
    debouncer = Debouncer(delay_ms=300)
    handler = IndexerEventHandler(debouncer)

    handler.on_modified(_mock_fs_event("src/config.yaml"))

    assert debouncer.drain() == []
