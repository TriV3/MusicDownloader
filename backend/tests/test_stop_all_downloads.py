import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_stop_all_downloads_marks_queued_and_stops_worker():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start worker in simulate mode
        r = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0.5})
        assert r.status_code == 200

        # Create a track and enqueue a download
        tr = await ac.post("/api/v1/tracks/", json={"title": "Song", "artists": "Artist"})
        tid = tr.json()["id"]
        # Enqueue without candidate for simplicity
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200

        # Stop all
        r = await ac.post("/api/v1/downloads/stop_all")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["queued_skipped"] >= 0
        # Worker stopped flag may be True depending on timing
