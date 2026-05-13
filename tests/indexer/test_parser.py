"""Tests for src/indexer/parser.py — symbol and call site extraction."""

import pathlib

from src.indexer.parser import parse_file

FIXTURE = str(pathlib.Path(__file__).parent.parent / "fixtures" / "simple_functions.py")


def test_parse_extracts_function_names():
    """Both top-level function names appear in the returned symbol list."""
    symbols, _ = parse_file(FIXTURE)
    names = {s.name for s in symbols}
    assert "compute_checksum" in names
    assert "strip_whitespace" in names


def test_parse_extracts_docstring():
    """The function with a docstring has it populated; the one without has None."""
    symbols, _ = parse_file(FIXTURE)
    by_name = {s.name: s for s in symbols}
    assert by_name["compute_checksum"].docstring is not None
    assert "SHA-256" in by_name["compute_checksum"].docstring
    assert by_name["strip_whitespace"].docstring is None


def test_parse_extracts_class_and_methods():
    """The class is kind='class'; its methods are kind='method'."""
    symbols, _ = parse_file(FIXTURE)
    kinds = {s.name: s.kind for s in symbols}
    assert kinds["FileProcessor"] == "class"
    assert kinds["read"] == "method"
    assert kinds["normalize"] == "method"


def test_parse_returns_empty_on_bad_file():
    """parse_file returns ([], []) for a nonexistent path without raising."""
    symbols, calls = parse_file("/nonexistent/path/does_not_exist.py")
    assert symbols == []
    assert calls == []
