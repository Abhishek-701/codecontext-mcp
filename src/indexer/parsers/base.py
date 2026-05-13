"""Abstract base class that all language parsers must implement."""

import logging
from abc import ABC, abstractmethod

from src.indexer.models import CallSite, Symbol

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Interface for language-specific AST parsers."""

    @abstractmethod
    def parse(self, file_path: str) -> tuple[list[Symbol], list[CallSite]]:
        """Parse a source file and return extracted symbols and call sites."""
