"""Watchdog event handler that filters filesystem events into the Debouncer."""

import logging
import time

from watchdog.events import FileSystemEventHandler

from src.watcher.debouncer import Debouncer
from src.watcher.events import FileChangeEvent, is_indexable

logger = logging.getLogger(__name__)


class IndexerEventHandler(FileSystemEventHandler):
    """Watchdog handler that filters and enqueues source file change events.

    Directory events and files that fail the is_indexable check are silently
    dropped. Qualifying events are wrapped as FileChangeEvent and handed to
    the Debouncer for coalescing.
    """

    def __init__(self, debouncer: Debouncer) -> None:
        """Initialise with a Debouncer that will collect filtered events."""
        super().__init__()
        self._debouncer = debouncer

    def on_modified(self, event) -> None:
        """Handle a file modification notification from watchdog."""
        self._handle(event, "modified")

    def on_created(self, event) -> None:
        """Handle a file creation notification from watchdog."""
        self._handle(event, "created")

    def on_deleted(self, event) -> None:
        """Handle a file deletion notification from watchdog."""
        self._handle(event, "deleted")

    def _handle(self, event, event_type: str) -> None:
        """Filter a raw watchdog event and enqueue it if indexable."""
        if event.is_directory:
            return
        if not is_indexable(event.src_path):
            return
        change = FileChangeEvent(
            file_path=event.src_path,
            event_type=event_type,
            timestamp=time.monotonic(),
        )
        self._debouncer.add(change)
        logger.debug(
            "Enqueued change event",
            extra={"file": event.src_path, "event_type": event_type},
        )
