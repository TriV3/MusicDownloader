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
    # First query should now include all artists (not just primary)
    assert "a, a & b" in qs[0].lower() or "a & b" in qs[0].lower()
    # Ensure no duplicate queries (case-insensitive)
    assert len(qs) == len(set(q.lower() for q in qs))


def test_build_search_queries_includes_all_artists_in_primary():
    """Test that primary query includes all artists, not just the first one."""
    qs = _build_search_queries(
        artists="Joshwa, Enzo is Burning",
        title="Night Moves",
        prefer_extended=False,
    )
    # First query should include both artists
    first_query = qs[0]
    assert "joshwa" in first_query.lower()
    assert "enzo is burning" in first_query.lower()
    assert "night moves" in first_query.lower()
    
    # Verify we have multiple query variants
    assert len(qs) >= 3
    
    # One of the queries should have the hyphen format with all artists
    hyphen_queries = [q for q in qs if " - " in q]
    assert len(hyphen_queries) >= 1
    assert any("joshwa, enzo is burning" in q.lower() for q in hyphen_queries)

