import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.utils.youtube_search import score_result, YouTubeResult
except Exception:
    from app.utils.youtube_search import score_result, YouTubeResult


def _res(channel: str):
    return YouTubeResult(
        external_id="vid",
        title="Daft Punk - One More Time (Official Video)",
        url="https://youtu.be/vid",
        channel=channel,
        duration_sec=320,
    )


def test_official_channel_bonus_vevo():
    # Baseline: random channel
    base = score_result("Daft Punk", "One More Time", 320000, _res("Random Channel"))
    vevo = score_result("Daft Punk", "One More Time", 320000, _res("DaftPunkVEVO"))
    assert vevo > base
    assert vevo - base >= 0.15  # significant boost


def test_official_channel_bonus_topic():
    base = score_result("Daft Punk", "One More Time", 320000, _res("Random Channel"))
    topic = score_result("Daft Punk", "One More Time", 320000, _res("Daft Punk - Topic"))
    assert topic > base
    assert topic - base >= 0.15


def test_artist_match_without_official_still_bonus():
    base = score_result("Daft Punk", "One More Time", 320000, _res("Random Channel"))
    fan = score_result("Daft Punk", "One More Time", 320000, _res("DaftPunkFans"))
    assert fan > base
    assert fan - base >= 0.05
