"""Realistic Python fixture used as an indexer test input."""

import hashlib


def compute_checksum(data: bytes) -> str:
    """Compute the SHA-256 hex digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def strip_whitespace(text: str) -> str:
    return text.strip()


class FileProcessor:
    """Handles reading and preprocessing of source files."""

    def read(self, path: str) -> bytes:
        """Read file contents as raw bytes."""
        with open(path, "rb") as fh:
            return fh.read()

    def normalize(self, content: bytes) -> str:
        return content.decode("utf-8").strip()
