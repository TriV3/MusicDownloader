import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("YOUTUBE_SEARCH_FAKE", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Test Song", artists="Artist", duration_ms=180000):
    r = await ac.post(
        "/api/v1/tracks/",
        json={
            "title": title,
            "artists": artists,
            "duration_ms": duration_ms,
            "normalized_title": title.lower(),
            "normalized_artists": artists.lower(),
        },
    )
    assert r.status_code == 200
    return r.json()["id"], duration_ms


@pytest.mark.asyncio
async def test_youtube_search_persist_and_prefer_extended():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, duration_ms = await _create_track(ac, title="My Track", artists="Cool Artist", duration_ms=180000)

        # Basic search with persistence
        r = await ac.get(f"/api/v1/tracks/{track_id}/youtube/search", params={"persist": True})
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 3
        # Scores should be present and sorted desc
        scores = [d["score"] for d in data]
        assert scores == sorted(scores, reverse=True)

        # Extended preference search (non-persist) should boost Extended Mix over Official when prefer_extended
        r2 = await ac.get(
            f"/api/v1/tracks/{track_id}/youtube/search",
            params={"persist": False, "prefer_extended": True},
        )
        assert r2.status_code == 200
        transient = r2.json()
        titles = [c["title"].lower() for c in transient]
        # Ensure an extended mix candidate exists
        assert any("extended" in t for t in titles)
        # Highest score should be extended or contain extended mix keyword
        top = transient[0]
        if not any(k in top["title"].lower() for k in ("extended", "club mix")):
            # If not, ensure at least second is (determinism across runs)
            assert any(k in transient[1]["title"].lower() for k in ("extended", "club mix"))

        # Re-run persisted search should not create duplicates (count stable)
        count_before = len(data)
        r3 = await ac.get(f"/api/v1/tracks/{track_id}/youtube/search", params={"persist": True})
        assert r3.status_code == 200
        data_again = r3.json()
        assert len(data_again) == count_before
