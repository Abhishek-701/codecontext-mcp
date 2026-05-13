"""Dataclasses used throughout the indexer layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Symbol:
    """A named code symbol extracted from a source file."""

    id: Optional[int]        # None before DB insert
    name: str
    qualified_name: str      # e.g. "auth.validator.validate_token"
    kind: str                # "function" | "class" | "method" | "import"
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str]
    language: str


@dataclass(frozen=True)
class CallSite:
    """A call-graph edge captured at a specific source location."""

    caller_name: str
    call_site_file: str
    call_site_line: int
    context_snippet: str     # 1-3 lines around the call site
    callee_name: str


@dataclass
class IndexResult:
    """Result of a single file indexing operation."""

    file_path: str
    skipped: bool            # True if content hash matched
    symbol_count: int
    elapsed_ms: float
    error: Optional[str]     # None if successful
