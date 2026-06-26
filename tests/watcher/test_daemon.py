"""Tests for watcher daemon observer selection."""

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from src.watcher import daemon


def test_use_polling_observer_false_by_default(monkeypatch):
    """Native observer is used when WATCH_USE_POLLING is unset."""
    monkeypatch.delenv("WATCH_USE_POLLING", raising=False)
    assert daemon._use_polling_observer() is False


def test_use_polling_observer_true_when_enabled(monkeypatch):
    """Polling mode is enabled for truthy WATCH_USE_POLLING values."""
    monkeypatch.setenv("WATCH_USE_POLLING", "true")
    assert daemon._use_polling_observer() is True


def test_create_observer_native(monkeypatch):
    """_create_observer returns Observer when polling is disabled."""
    monkeypatch.delenv("WATCH_USE_POLLING", raising=False)
    assert isinstance(daemon._create_observer(), Observer)


def test_create_observer_polling(monkeypatch):
    """_create_observer returns PollingObserver when polling is enabled."""
    monkeypatch.setenv("WATCH_USE_POLLING", "1")
    assert isinstance(daemon._create_observer(), PollingObserver)
