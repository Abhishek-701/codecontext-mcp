"""Dataclasses returned by the query layer (exact.py and semantic.py)."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CallSite:
    """A call-graph edge as returned by the query engine.

    Distinct from indexer.models.CallSite: this version carries caller_file
    (resolved from the JOIN in FIND_CALLERS) and omits callee_name.
    """

    caller_name: str
    caller_file: str
    call_site_file: str
    call_site_line: int
    context_snippet: str


@dataclass(frozen=True)
class Commit:
    """A git commit that touched the lines of a queried symbol."""

    hash: str
    author: str
    date: str          # ISO 8601 string, as returned by git %aI
    message: str
    lines_changed: int


@dataclass(frozen=True)
class SearchResult:
    """A symbol match returned by pgvector semantic search."""

    name: str
    qualified_name: str
    kind: str
    file_path: str
    line_start: int
    docstring: Optional[str]
    similarity: float  # cosine similarity 0–1, higher is closer


@dataclass(frozen=True)
class FileSymbol:
    """A symbol entry in a file outline, ordered by line_start."""

    name: str
    kind: str
    line_start: int
    line_end: int
    docstring: Optional[str]
