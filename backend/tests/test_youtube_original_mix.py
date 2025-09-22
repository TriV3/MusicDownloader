import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils.youtube_search import (
        _build_search_queries,
        YouTubeResult,
        score_result,
    )
except Exception:  # pragma: no cover
    from app.utils.youtube_search import (
        _build_search_queries,
        YouTubeResult,
        score_result,
    )


def test_query_builder_adds_original_mix_variant():
    queries = _build_search_queries("Artist", "Title", prefer_extended=True)
    joined = " | ".join(q.lower() for q in queries)
    assert "artist - title extended mix" in joined
    assert "artist - title original mix" in joined


def test_original_mix_scored_as_extended():
    r = YouTubeResult(
        external_id="x1",
        title="Artist - Title (Original Mix)",
        url="https://y/x1",
        channel="Artist",
        duration_sec=200,
    )
    s = score_result("Artist", "Title", track_duration_ms=180000, result=r, prefer_extended=True)
    # Should have a noticeable extended-related uplift vs non-extended
    assert s > 0.35
