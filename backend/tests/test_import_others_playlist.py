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
async def test_import_creates_others_and_membership():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Run an import of a single track
        rows = [{"artists": "Tester", "title": "Lonely Track", "genre": "House", "bpm": 124, "duration": "3:21"}]
        files = {"file": ("tracks.json", json.dumps(rows), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "false"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 1

        # Fetch playlists, ensure 'Others' exists and is selected
        r2 = await ac.get("/api/v1/playlists/?selected=true")
        assert r2.status_code == 200
        playlists = r2.json()
        names = [p.get("name") for p in playlists]
        assert "Others" in names
        others = next(p for p in playlists if p.get("name") == "Others")

        # Fetch tracks to get the new track id
        r3 = await ac.get("/api/v1/tracks/?limit=10")
        assert r3.status_code == 200
        tracks = r3.json()
        assert len(tracks) >= 1
        tid = tracks[-1]["id"]

        # Check playlist memberships endpoint
        r4 = await ac.post("/api/v1/playlists/memberships", json={"track_ids": [tid]})
        assert r4.status_code == 200
        memberships = r4.json()
        assert str(tid) in memberships or tid in memberships
        arr = memberships.get(str(tid)) or memberships.get(tid)
        assert isinstance(arr, list)
        # Ensure 'Others' membership is present
        assert any(m.get("playlist_id") == others.get("id") for m in arr)
