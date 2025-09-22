import os
import types
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# This test simulates a VideosSearch.next() that returns a boolean to ensure our code doesn't crash.

def test_youtubesearchpython_handles_bool_next(monkeypatch):
    monkeypatch.setenv("YOUTUBE_SEARCH_PROVIDER", "yts_python")
    monkeypatch.setenv("YOUTUBE_SEARCH_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_FALLBACK_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_PAGE_SIZE", "2")
    monkeypatch.setenv("YOUTUBE_SEARCH_MAX_PAGES", "3")

    # Build a fake VideosSearch-like object
    class FakeVS:
        def __init__(self, q, limit=None, language=None, region=None):
            self.calls = 0
        def result(self):
            # First page returns a dict with results
            return {
                "result": [
                    {"id": "a1", "title": "Artist - Title", "link": "https://y/a1", "channel": {"name": "Artist"}, "duration": "3:00"},
                    {"id": "a2", "title": "Other", "link": "https://y/a2", "channel": {"name": "Artist"}, "duration": "2:59"},
                ]
            }
        def next(self):
            # Second page returns a boolean instead of dict — simulate library quirk
            return False

    try:
        from backend.app.utils import youtube_search as ys
    except Exception:  # pragma: no cover
        import app.utils.youtube_search as ys

    monkeypatch.setattr(ys, "VideosSearch", FakeVS, raising=True)

    out = ys.search_youtube("Artist", "Title", track_duration_ms=None, prefer_extended=False, limit=5)
    # Should not crash and should return items from the first page, filtered and scored
    assert isinstance(out, list)
    assert len(out) >= 1
