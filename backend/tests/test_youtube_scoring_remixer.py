import os
import pytest

os.environ.setdefault("YOUTUBE_SEARCH_FAKE", "1")

from backend.app.utils.youtube_search import get_score_components


@pytest.mark.skip(reason="Old scoring system - extended/remix detection now handled by unified ranking with different scoring model")
def test_remix_bonus_and_softer_penalty_in_extended_mode():
    comps = get_score_components(
        norm_query="angrybaby hold you sunday scaries",
        norm_title="angrybaby hold you (sunday scaries remix)",
        primary_artist="Angrybaby",
        track_duration_ms=None,
        result_duration_sec=None,
        result_title="HOLD YOU (Sunday Scaries Remix)",
        result_channel="Some Channel",
        prefer_extended=True,
    )
    text, duration, ext, channel, tokens_penalty, keywords_penalty = comps
    assert ext >= 0.30
    # Non-primary token penalties should be softened in extended mode
    assert tokens_penalty >= -0.05
