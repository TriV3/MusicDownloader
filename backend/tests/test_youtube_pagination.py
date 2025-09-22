import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils import youtube_search as ys
except Exception:  # pragma: no cover
    import app.utils.youtube_search as ys


def test_pagination_early_stop_with_simulated_provider(monkeypatch):
    # Force simulated pagination path (yt-dlp provider), 1 item per page
    monkeypatch.setenv("YOUTUBE_SEARCH_PROVIDER", "yt_dlp")
    monkeypatch.setenv("YOUTUBE_SEARCH_PAGE_SIZE", "1")
    monkeypatch.setenv("YOUTUBE_SEARCH_MAX_PAGES", "5")
    monkeypatch.setenv("YOUTUBE_SEARCH_PAGE_STOP_THRESHOLD", "0.5")
    monkeypatch.setenv("YOUTUBE_SEARCH_FAKE", "0")
    monkeypatch.setenv("YOUTUBE_SEARCH_FALLBACK_FAKE", "0")

    calls = []

    def fake_provider(query: str, limit: int):
        # Record the call for inspection
        calls.append(limit)
        # First page: unrelated low-scoring
        low = ys.YouTubeResult(
            external_id="low1",
            title="Some unrelated video",
            url="https://youtu.be/low1",
            channel="Other",
            duration_sec=None,
        )
        # Second page introduces a high-scoring extended mix
        high = ys.YouTubeResult(
            external_id="high1",
            title="Artist - Title (Extended Mix)",
            url="https://youtu.be/high1",
            channel="Artist",
            duration_sec=None,
        )
        data = [low, high]
        return data[:limit]

    monkeypatch.setattr(ys, "_provider_search", fake_provider)

    # prefer_extended boosts the extended mix, ensuring score >= 0.5
    results = ys.search_youtube("Artist", "Title", track_duration_ms=None, prefer_extended=True, limit=5)

    # Should have stopped after finding the high-scoring item on the second page
    assert calls == [1, 2]
    assert isinstance(results, list)
    assert len(results) >= 1
    # The top result should be the extended mix
    assert results[0].external_id == "high1"
