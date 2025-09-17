import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils.youtube_search import score_result, YouTubeResult
except Exception:  # pragma: no cover
    from app.utils.youtube_search import score_result, YouTubeResult


def R(title: str):
    return YouTubeResult(
        external_id="vid",
        title=title,
        url="https://youtu.be/vid",
        channel="Random Channel",
        duration_sec=180,
    )


def test_keywords_penalty_lyrics_live_cover():
    base = score_result("Artist", "Song", 180000, R("Artist - Song (Official Video)"))
    lyrics = score_result("Artist", "Song", 180000, R("Artist - Song (Lyrics)"))
    live = score_result("Artist", "Song", 180000, R("Artist - Song (Live)"))
    cover = score_result("Artist", "Song", 180000, R("Artist - Song (Cover)"))
    karaoke = score_result("Artist", "Song", 180000, R("Artist - Song (Karaoke Version)"))

    assert lyrics < base
    assert live < base
    assert cover < base
    assert karaoke < base


def test_audio_only_slight_penalty_when_not_official():
    # When channel bonus is low, 'audio' should incur a small penalty
    audio = score_result("Artist", "Song", 180000, R("Artist - Song (Audio)"))
    video = score_result("Artist", "Song", 180000, R("Artist - Song (Video)") )
    assert audio <= video
