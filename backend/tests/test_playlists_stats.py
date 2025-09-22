import os
import pytest
from httpx import AsyncClient

# Ensure in-memory DB for isolation
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_playlists_stats_basics():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/v1/playlists/stats")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # With empty DB we should at least have the 'Other' bucket
        assert any(it.get("provider") == "other" for it in data)
        other = next(it for it in data if it.get("provider") == "other")
        assert set(other.keys()) >= {"playlist_id", "name", "provider", "total_tracks", "downloaded_tracks", "not_downloaded_tracks"}
        # Counts should be zero in a fresh DB
        assert other["total_tracks"] == 0
        assert other["downloaded_tracks"] == 0
        assert other["not_downloaded_tracks"] == 0
