"""Event debouncer that coalesces rapid filesystem changes per file path."""

import logging
import time

from src.watcher.events import FileChangeEvent

logger = logging.getLogger(__name__)


class Debouncer:
    """Collects FileChangeEvents and releases them after a settling delay.

    Keyed by file_path — if multiple events arrive for the same file within
    the delay window, only the last one is kept (last-write-wins). drain() is
    meant to be called on a poll loop; no threads or asyncio are used.
    """

    def __init__(self, delay_ms: int = 300) -> None:
        """Initialise with a debounce delay in milliseconds."""
        self._delay_s: float = delay_ms / 1000.0
        self._pending: dict[str, FileChangeEvent] = {}

    def add(self, event: FileChangeEvent) -> None:
        """Store event keyed by file_path; a newer event for the same path replaces the old one."""
        self._pending[event.file_path] = event

    def drain(self) -> list[FileChangeEvent]:
        """Return and remove all events whose timestamp is older than the delay window."""
        now = time.monotonic()
        ready = [
            e for e in self._pending.values()
            if now - e.timestamp >= self._delay_s
        ]
        for e in ready:
            del self._pending[e.file_path]
        logger.debug(
            "Drained debouncer",
            extra={"ready": len(ready), "still_pending": len(self._pending)},
        )
        return ready
