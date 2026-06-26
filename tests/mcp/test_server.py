"""Unit tests for MCP tool handlers in src/mcp/server.py."""

from unittest.mock import AsyncMock

import pytest

from src.indexer.models import Symbol
from src.mcp import server
from src.query.models import CallSite, FileSymbol, SearchResult


@pytest.fixture(autouse=True)
def mock_pool():
    """Attach a dummy pool; query functions are mocked so the value is unused."""
    server.mcp.pool = object()
    yield


async def test_get_symbol_returns_dict_on_success(monkeypatch):
    """get_symbol serializes a Symbol to a dict with no error key."""
    fake_symbol = Symbol(
        id=1,
        name="validate_token",
        qualified_name="auth.validator.validate_token",
        kind="function",
        file_path="auth/validator.py",
        line_start=42,
        line_end=61,
        docstring="Validates a JWT token.",
        language="python",
    )
    monkeypatch.setattr(
        "src.mcp.server.query_exact.get_symbol",
        AsyncMock(return_value=fake_symbol),
    )
    result = await server.get_symbol("validate_token", "/repo")
    assert result["name"] == "validate_token"
    assert result["kind"] == "function"
    assert result["file_path"] == "auth/validator.py"
    assert "error" not in result


async def test_get_symbol_returns_error_on_not_found(monkeypatch):
    """get_symbol returns SYMBOL_NOT_FOUND when the query layer returns None."""
    monkeypatch.setattr(
        "src.mcp.server.query_exact.get_symbol",
        AsyncMock(return_value=None),
    )
    result = await server.get_symbol("missing_sym", "/repo")
    assert "error" in result
    assert result["code"] == "SYMBOL_NOT_FOUND"


async def test_get_symbol_rejects_blank_name(monkeypatch):
    """get_symbol rejects blank name without calling the query layer."""
    mock_get_symbol = AsyncMock()
    monkeypatch.setattr("src.mcp.server.query_exact.get_symbol", mock_get_symbol)
    result = await server.get_symbol("  ", "/repo")
    assert result["code"] == "INVALID_INPUT"
    mock_get_symbol.assert_not_called()


async def test_find_callers_returns_shaped_response(monkeypatch):
    """find_callers wraps CallSite objects in a shaped response dict."""
    callers = [
        CallSite(
            caller_name="handle_request",
            caller_file="api/handlers.py",
            call_site_file="api/handlers.py",
            call_site_line=88,
            context_snippet="validate_token(token)",
        ),
        CallSite(
            caller_name="other_fn",
            caller_file="api/other.py",
            call_site_file="api/other.py",
            call_site_line=12,
            context_snippet="validate_token(x)",
        ),
    ]
    monkeypatch.setattr(
        "src.mcp.server.query_exact.find_callers",
        AsyncMock(return_value=callers),
    )
    result = await server.find_callers("validate_token", "/repo")
    assert result["caller_count"] == 2
    assert len(result["callers"]) == 2
    assert result["callers"][0]["call_site_line"] == 88
    assert "error" not in result


async def test_find_callers_returns_empty_list_not_error(monkeypatch):
    """find_callers returns an empty callers list without an error key."""
    monkeypatch.setattr(
        "src.mcp.server.query_exact.find_callers",
        AsyncMock(return_value=[]),
    )
    result = await server.find_callers("validate_token", "/repo")
    assert result["caller_count"] == 0
    assert result["callers"] == []
    assert "error" not in result


async def test_get_change_history_clamps_limit(monkeypatch):
    """get_change_history clamps limit to 50 before calling the query layer."""
    mock_history = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "src.mcp.server.query_exact.get_change_history",
        mock_history,
    )
    result = await server.get_change_history("sym", "/repo", limit=999)
    mock_history.assert_called_once_with("sym", "/repo", server.mcp.pool, 50)
    assert result["commit_count"] == 0
    assert "error" not in result


async def test_semantic_search_returns_shaped_response(monkeypatch):
    """semantic_search wraps SearchResult objects in a shaped response dict."""
    results = [
        SearchResult(
            name="handle_auth_error",
            qualified_name="api.errors.handle_auth_error",
            kind="function",
            file_path="api/errors.py",
            line_start=14,
            docstring="Handles auth errors.",
            similarity=0.87,
        ),
        SearchResult(
            name="check_token",
            qualified_name="auth.check_token",
            kind="function",
            file_path="auth/token.py",
            line_start=3,
            docstring=None,
            similarity=0.72,
        ),
    ]
    monkeypatch.setattr(
        "src.mcp.server.query_semantic.semantic_search",
        AsyncMock(return_value=results),
    )
    result = await server.semantic_search("auth errors", "/repo")
    assert result["result_count"] == 2
    assert len(result["results"]) == 2
    assert all("similarity" in r for r in result["results"])
    assert "error" not in result


async def test_get_file_outline_returns_file_not_indexed_on_empty(monkeypatch):
    """get_file_outline returns FILE_NOT_INDEXED when the query layer returns []."""
    monkeypatch.setattr(
        "src.mcp.server.query_exact.get_file_outline",
        AsyncMock(return_value=[]),
    )
    result = await server.get_file_outline("auth/validator.py", "/repo")
    assert result["code"] == "FILE_NOT_INDEXED"
    assert "error" in result


async def test_get_file_outline_returns_symbols_in_response(monkeypatch):
    """get_file_outline serializes FileSymbol objects into the response."""
    symbols = [
        FileSymbol(
            name="TokenValidator",
            kind="class",
            line_start=8,
            line_end=95,
            docstring="Validates tokens.",
        ),
        FileSymbol(
            name="validate_token",
            kind="method",
            line_start=42,
            line_end=61,
            docstring="Validates a JWT token.",
        ),
        FileSymbol(
            name="decode_token",
            kind="function",
            line_start=63,
            line_end=70,
            docstring=None,
        ),
    ]
    monkeypatch.setattr(
        "src.mcp.server.query_exact.get_file_outline",
        AsyncMock(return_value=symbols),
    )
    result = await server.get_file_outline("auth/validator.py", "/repo")
    assert result["symbol_count"] == 3
    assert len(result["symbols"]) == 3
    assert result["symbols"][0]["name"] == "TokenValidator"
    assert "error" not in result
