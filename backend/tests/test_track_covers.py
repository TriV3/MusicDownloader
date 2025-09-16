import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("YOUTUBE_SEARCH_FAKE", "1")

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


async def _create_track(ac: AsyncClient, title="Song", artists="Artist", duration_ms=180000):
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
    body = r.json()
    return body["id"], duration_ms


@pytest.mark.asyncio
async def test_youtube_search_persist_sets_cover_if_missing():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid, _ = await _create_track(ac, title="Alpha", artists="Artist A")
        # Ensure no cover yet
        r0 = await ac.get(f"/api/v1/tracks/{tid}")
        assert r0.status_code == 200 and r0.json().get("cover_url") in (None, "")

        # Run YouTube search with persist
        r = await ac.get(f"/api/v1/tracks/{tid}/youtube/search", params={"prefer_extended": "false", "persist": "true"})
        assert r.status_code == 200, r.text

        r2 = await ac.get(f"/api/v1/tracks/{tid}")
        assert r2.status_code == 200
        cover = r2.json().get("cover_url")
        assert isinstance(cover, str) and cover.startswith("https://img.youtube.com/vi/")


@pytest.mark.asyncio
async def test_choose_candidate_sets_cover_if_missing():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid, _ = await _create_track(ac, title="Beta", artists="Artist B")
        # Create a youtube candidate
        r1 = await ac.post(
            "/api/v1/candidates/",
            json={
                "track_id": tid,
                "provider": "youtube",
                "external_id": "fake2",
                "url": "https://youtu.be/fake2",
                "title": "Beta (Extended Mix)",
                "score": 0.9,
                "duration_sec": 200,
            },
        )
        assert r1.status_code == 200
        cand = r1.json()

        # Choose it -> cover should be set
        r2 = await ac.post(f"/api/v1/candidates/{cand['id']}/choose")
        assert r2.status_code == 200
        r3 = await ac.get(f"/api/v1/tracks/{tid}")
        cover = r3.json().get("cover_url")
        assert isinstance(cover, str) and "/img.youtube.com/vi/" in cover


@pytest.mark.asyncio
async def test_cover_refresh_endpoint_noop_without_spotify():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid, _ = await _create_track(ac, title="Gamma", artists="Artist C")
        # No spotify identity; create chosen youtube candidate for fallback
        r1 = await ac.post(
            "/api/v1/candidates/",
            json={
                "track_id": tid,
                "provider": "youtube",
                "external_id": "fake1",
                "url": "https://youtu.be/fake1",
                "title": "Gamma (Official Video)",
                "score": 0.8,
                "duration_sec": 180,
            },
        )
        cid = r1.json()["id"]
        await ac.post(f"/api/v1/candidates/{cid}/choose")

        # Clear cover to simulate missing
        # Update track directly via PUT
        r_put = await ac.put(f"/api/v1/tracks/{tid}", json={
            "title": "Gamma",
            "artists": "Artist C",
            "normalized_title": "Gamma".lower(),
            "normalized_artists": "Artist C".lower(),
            "cover_url": None,
        })
        assert r_put.status_code == 200

        r = await ac.post(f"/api/v1/tracks/{tid}/cover/refresh")
        assert r.status_code == 200
        body = r.json()
        # Should pick up chosen youtube thumbnail as fallback
        assert isinstance(body.get("cover_url"), str) and "/img.youtube.com/vi/" in body["cover_url"]
