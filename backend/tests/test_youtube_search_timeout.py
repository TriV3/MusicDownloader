import os
import subprocess
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils.youtube_search import search_youtube
except Exception:  # pragma: no cover
    from app.utils.youtube_search import search_youtube


def test_search_returns_empty_on_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", ["yt-dlp"]), timeout=kwargs.get("timeout", 0.1))
    monkeypatch.setenv("YOUTUBE_SEARCH_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_FALLBACK_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_TIMEOUT", "0.1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = search_youtube("Artist", "Title", track_duration_ms=None, prefer_extended=False, limit=5)
    assert isinstance(res, list)
    assert res == []


def test_search_uses_fallback_when_enabled(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", ["yt-dlp"]), timeout=kwargs.get("timeout", 0.1))
    monkeypatch.setenv("YOUTUBE_SEARCH_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_FALLBACK_FAKE", "1")
    monkeypatch.setenv("YOUTUBE_SEARCH_TIMEOUT", "0.1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = search_youtube("Artist", "Title", track_duration_ms=None, prefer_extended=False, limit=5)
    assert isinstance(res, list)
    assert len(res) > 0
