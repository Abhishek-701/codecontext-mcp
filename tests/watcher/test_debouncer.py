"""Unit tests for src/watcher/debouncer.py — Debouncer coalescing logic."""

import time

from src.watcher.debouncer import Debouncer
from src.watcher.events import FileChangeEvent

_FILE = "src/auth/validator.py"


def _make_event(event_type: str = "modified", age_s: float = 0.0) -> FileChangeEvent:
    """Build a FileChangeEvent with a controllable timestamp age."""
    return FileChangeEvent(
        file_path=_FILE,
        event_type=event_type,
        timestamp=time.monotonic() - age_s,
    )


def test_drain_returns_nothing_before_delay():
    """A freshly added event must not drain before the delay window has elapsed."""
    debouncer = Debouncer(delay_ms=300)
    debouncer.add(_make_event(age_s=0.0))
    assert debouncer.drain() == []


def test_drain_returns_event_after_delay():
    """An event whose timestamp is older than the delay window must be drained."""
    debouncer = Debouncer(delay_ms=300)
    debouncer.add(_make_event(age_s=0.4))
    result = debouncer.drain()
    assert len(result) == 1
    assert result[0].file_path == _FILE


def test_last_event_wins_for_same_file():
    """When two events arrive for the same file_path, only the later one is kept."""
    debouncer = Debouncer(delay_ms=300)
    debouncer.add(FileChangeEvent(file_path=_FILE, event_type="created", timestamp=time.monotonic() - 0.4))
    debouncer.add(FileChangeEvent(file_path=_FILE, event_type="modified", timestamp=time.monotonic() - 0.4))
    result = debouncer.drain()
    assert len(result) == 1
    assert result[0].event_type == "modified"


def test_drain_removes_returned_events():
    """Events returned by drain() must not appear in a subsequent drain() call."""
    debouncer = Debouncer(delay_ms=300)
    debouncer.add(_make_event(age_s=0.4))
    debouncer.drain()
    assert debouncer.drain() == []
