"""Filesystem change event dataclass and indexability filter."""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: frozenset = frozenset({".py", ".js", ".ts"})

_EXCLUDED_DIRS: frozenset = frozenset({"node_modules", "__pycache__"})


@dataclass(frozen=True)
class FileChangeEvent:
    """A filesystem change detected for a single source file."""

    file_path: str
    event_type: str   # "created" | "modified" | "deleted"
    timestamp: float  # time.monotonic() at detection


def is_indexable(file_path: str) -> bool:
    """Return True if the file should be indexed based on extension and path structure.

    Rejects files outside SUPPORTED_EXTENSIONS, inside hidden directories
    (any component starting with '.'), and inside node_modules or __pycache__.
    """
    path = Path(file_path)
    if path.suffix not in SUPPORTED_EXTENSIONS:
        return False
    for part in path.parts:
        if part.startswith("."):
            return False
        if part in _EXCLUDED_DIRS:
            return False
    return True
