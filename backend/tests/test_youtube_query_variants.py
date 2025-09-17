import os
import pytest

os.environ.setdefault("YOUTUBE_SEARCH_FAKE", "1")

from backend.app.utils.youtube_search import _build_search_queries


def test_build_search_queries_includes_remixer_and_extended():
    qs = _build_search_queries(
        artists="Angrybaby, Sunday Scaries",
        title="HOLD YOU - Sunday Scaries Remix",
        prefer_extended=True,
    )
    joined = " || ".join(qs).lower()
    assert "hold you sunday scaries" in joined
    assert "hold you remix" in joined
    assert "hold you extended mix" in joined
    assert "angrybaby hold you" in joined


def test_build_search_queries_deduplicates_and_orders():
    qs = _build_search_queries("A, A & B", "Song (A Remix)", prefer_extended=False)
    assert qs[0].lower().startswith("a song")
    assert len(qs) == len(set(q.lower() for q in qs))
