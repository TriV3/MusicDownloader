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
        # Initially, capture the count of 'Other' bucket (may be absent)
        r = await ac.get("/api/v1/playlists/stats")
        assert r.status_code == 200
        stats = r.json()
        initial_other = next((s for s in stats if s.get("name") == "Other"), None)
        initial_other_total = initial_other.get("total_tracks", 0) if initial_other else 0

        # Import a manual track with dry_run=false; it goes to 'Others' playlist
        rows = [{"artists": "Tester", "title": "In Others", "genre": "House", "bpm": 124, "duration": "3:21"}]
        files = {"file": ("tracks.json", json.dumps(rows), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "false"})
        assert r.status_code == 200

        # Now there are no manual-without-playlist tracks; 'Other' bucket should not increase
        r2 = await ac.get("/api/v1/playlists/stats")
        assert r2.status_code == 200
        stats2 = r2.json()
        other2 = next((s for s in stats2 if s.get("name") == "Other"), None)
        total2 = other2.get("total_tracks", 0) if other2 else 0
        assert total2 == initial_other_total

        # Create a manual track (auto-creates a manual identity) without linking to any playlist
        r3 = await ac.post("/api/v1/tracks/", json={"artists": "Free", "title": "Orphan Manual"})
        assert r3.status_code == 200

        # Now the 'Other' bucket total should increase by at least 1
        r4 = await ac.get("/api/v1/playlists/stats")
        assert r4.status_code == 200
        stats3 = r4.json()
        other3 = next((s for s in stats3 if s.get("name") == "Other"), None)
        total3 = other3.get("total_tracks", 0) if other3 else 0
        assert total3 >= initial_other_total + 1
