import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
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
    return r.json()["id"], duration_ms


@pytest.mark.asyncio
async def test_candidates_crud_sort_and_choose():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, duration_ms = await _create_track(ac, title="Alpha", artists="Artist A", duration_ms=200000)

        # Create candidates with different scores and durations
        payloads = [
            {"track_id": track_id, "provider": "youtube", "external_id": "vid1", "url": "http://y/1", "title": "Alpha (Official)", "score": 0.8, "duration_sec": 200},
            {"track_id": track_id, "provider": "youtube", "external_id": "vid2", "url": "http://y/2", "title": "Alpha (Live)", "score": 0.5, "duration_sec": 205},
            {"track_id": track_id, "provider": "youtube", "external_id": "vid3", "url": "http://y/3", "title": "Alpha (Remix)", "score": 0.9, "duration_sec": 198},
        ]
        for p in payloads:
            r = await ac.post("/api/v1/candidates/", json=p)
            assert r.status_code == 200

        # List default sort (score desc)
        r = await ac.get("/api/v1/candidates/", params={"track_id": track_id})
        assert r.status_code == 200
        data = r.json()
        scores = [c["score"] for c in data]
        assert scores == sorted(scores, reverse=True)

        # Sort by duration delta
        r2 = await ac.get("/api/v1/candidates/", params={"track_id": track_id, "sort": "duration_delta"})
        assert r2.status_code == 200
        data2 = r2.json()
        deltas = [c["duration_delta_sec"] for c in data2]
        # Ensure ascending (None last if any)
        assert deltas == sorted(d for d in deltas if d is not None) + [d for d in deltas if d is None]

        # Choose a candidate
        chosen_id = data[0]["id"]
        r3 = await ac.post(f"/api/v1/candidates/{chosen_id}/choose")
        assert r3.status_code == 200
        # Ensure only one chosen
        r4 = await ac.get("/api/v1/candidates/", params={"track_id": track_id})
        chosen_flags = [c["chosen"] for c in r4.json()]
        assert sum(1 for f in chosen_flags if f) == 1

        # Delete one
        del_id = data[1]["id"]
        r5 = await ac.delete(f"/api/v1/candidates/{del_id}")
        assert r5.status_code == 200