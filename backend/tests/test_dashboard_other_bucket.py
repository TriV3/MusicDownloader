import os
import json
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


@pytest.mark.asyncio
async def test_stats_other_bucket_hidden_when_empty():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Initially, no tracks, so stats should not include 'Other' bucket
        r = await ac.get("/api/v1/playlists/stats")
        assert r.status_code == 200
        stats = r.json()
        assert all(s.get("name") != "Other" for s in stats)

        # Import a manual track with dry_run=false; it goes to 'Others' playlist
        rows = [{"artists": "Tester", "title": "In Others", "genre": "House", "bpm": 124, "duration": "3:21"}]
        files = {"file": ("tracks.json", json.dumps(rows), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "false"})
        assert r.status_code == 200

        # Now there are no manual-without-playlist tracks; 'Other' bucket should remain hidden
        r2 = await ac.get("/api/v1/playlists/stats")
        assert r2.status_code == 200
        stats2 = r2.json()
        assert all(s.get("name") != "Other" for s in stats2)

        # Create a manual track (auto-creates a manual identity) without linking to any playlist
        r3 = await ac.post("/api/v1/tracks/", json={"artists": "Free", "title": "Orphan Manual"})
        assert r3.status_code == 200

        # Now the 'Other' bucket should appear with at least 1 total
        r4 = await ac.get("/api/v1/playlists/stats")
        assert r4.status_code == 200
        stats3 = r4.json()
        names = [s.get("name") for s in stats3]
        assert "Other" in names
