import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils.youtube_search import get_score_components
except Exception:  # pragma: no cover
    from app.utils.youtube_search import get_score_components


def test_extended_bonus_is_greater_than_channel_bonus_when_prefer_extended():
    text, duration, ext, channel, tokens_penalty, keywords_penalty = get_score_components(
        norm_query="artist title",
        norm_title="artist title extended mix",
        primary_artist="Artist",
        track_duration_ms=None,
        result_duration_sec=None,
        result_title="Artist - Title (Extended Mix)",
        result_channel="Artist Official",
        prefer_extended=True,
    )
    assert ext > 0.0
    assert channel >= 0.0
    assert ext > channel, f"Expected extended bonus ({ext}) to be greater than channel bonus ({channel})"
