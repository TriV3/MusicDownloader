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
        # 'Other' bucket can be absent; when present it must have expected keys and consistent counts
        if any(it.get("provider") == "other" for it in data):
            other = next(it for it in data if it.get("provider") == "other")
            assert set(other.keys()) >= {"playlist_id", "name", "provider", "total_tracks", "downloaded_tracks", "not_downloaded_tracks"}
            total = other.get("total_tracks", 0)
            downloaded = other.get("downloaded_tracks", 0)
            not_downloaded = other.get("not_downloaded_tracks", 0)
            assert total >= 0 and downloaded >= 0 and not_downloaded >= 0
            assert not_downloaded == max(0, total - downloaded)
