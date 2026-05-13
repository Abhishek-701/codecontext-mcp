"""Unit tests for src/watcher/events.py — is_indexable filter."""

from src.watcher.events import is_indexable


def test_is_indexable_accepts_python_files():
    """Standard .py path with no excluded components should be accepted."""
    assert is_indexable("src/auth/validator.py") is True


def test_is_indexable_accepts_js_files():
    """Standard .js path with no excluded components should be accepted."""
    assert is_indexable("frontend/app.js") is True


def test_is_indexable_rejects_hidden_directories():
    """Files inside any hidden directory (component starting with '.') must be rejected."""
    assert is_indexable(".git/hooks/pre-commit") is False


def test_is_indexable_rejects_node_modules():
    """Files inside node_modules must be rejected regardless of extension."""
    assert is_indexable("node_modules/lodash/index.js") is False


def test_is_indexable_rejects_pycache():
    """Files inside __pycache__ must be rejected regardless of extension."""
    assert is_indexable("src/__pycache__/parser.cpython-312.pyc") is False


def test_is_indexable_rejects_unsupported_extension():
    """Files with extensions outside SUPPORTED_EXTENSIONS must be rejected."""
    assert is_indexable("src/config.yaml") is False
