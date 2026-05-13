"""Dispatch table mapping file extensions to language parser classes."""

import logging
import pathlib
from typing import Optional

from src.indexer.models import CallSite, Symbol
from src.indexer.parsers.base import BaseParser
from src.indexer.parsers.python import PythonParser

logger = logging.getLogger(__name__)

LANGUAGE_MAP: dict[str, type[BaseParser]] = {
    ".py": PythonParser,
}


def get_parser(file_path: str) -> Optional[BaseParser]:
    """Return a parser instance for the given file's extension, or None if unsupported."""
    ext = pathlib.Path(file_path).suffix
    parser_class = LANGUAGE_MAP.get(ext)
    if parser_class is None:
        return None
    return parser_class()


def parse_file(file_path: str) -> tuple[list[Symbol], list[CallSite]]:
    """Parse a source file and return symbols and call sites; returns ([], []) for unsupported types."""
    parser = get_parser(file_path)
    if parser is None:
        logger.debug("No parser for file", extra={"file": file_path})
        return [], []
    return parser.parse(file_path)
