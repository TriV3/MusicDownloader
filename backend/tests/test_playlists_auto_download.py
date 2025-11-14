import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("YOUTUBE_SEARCH_FALLBACK_FAKE", "1")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_auto_download_playlist(monkeypatch):
    # Ensure worker is running in simulate mode
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0.01})
        assert r.status_code == 200

        # Create two tracks and a playlist, link them
        r = await ac.post("/api/v1/tracks/", json={"title": "Song A", "artists": "Artist 1"})
        assert r.status_code == 200
        t1 = r.json()["id"]
        r = await ac.post("/api/v1/tracks/", json={"title": "Song B (Extended Mix)", "artists": "Artist 2"})
        assert r.status_code == 200
        t2 = r.json()["id"]

        r = await ac.post("/api/v1/playlists/", json={"provider": "spotify", "name": "MyList", "selected": True})
        assert r.status_code == 200
        pl_id = r.json()["id"]

        # Link tracks to playlist
        r = await ac.post("/api/v1/playlist_tracks/", json={"playlist_id": pl_id, "track_id": t1, "position": 1})
        assert r.status_code == 200
        r = await ac.post("/api/v1/playlist_tracks/", json={"playlist_id": pl_id, "track_id": t2, "position": 2})
        assert r.status_code == 200

        # Call auto_download with sync=true to get detailed results in tests
        r = await ac.post(f"/api/v1/playlists/{pl_id}/auto_download?prefer_extended=true&sync=true")
        assert r.status_code == 200
        summary = r.json()
        assert summary["playlist_id"] == pl_id
        assert summary["total_tracks"] == 2
        # Some tracks may be marked enqueued (or already if fake path chosen later); we just assert any progress
        assert summary["enqueued"] >= 1

        # Wait until worker idle
        await ac.post("/api/v1/downloads/_wait_idle", params={"timeout": 1.5})
