import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_stats_only_selected_by_default():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create two spotify playlists, one selected, one not
        r = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "name": "PL A",
            "selected": True,
        })
        assert r.status_code == 200
        pl_selected = r.json()["id"]

        r = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "name": "PL B",
            "selected": False,
        })
        assert r.status_code == 200
        pl_unselected = r.json()["id"]

        # By default selected_only=True
        r = await ac.get("/api/v1/playlists/stats")
        assert r.status_code == 200
        data = r.json()
        names = {it["name"] for it in data if it.get("playlist_id") is not None}
        assert "PL A" in names
        assert "PL B" not in names

        # Explicit selected_only=true yields same
        r = await ac.get("/api/v1/playlists/stats?selected_only=true")
        assert r.status_code == 200
        data = r.json()
        names = {it["name"] for it in data if it.get("playlist_id") is not None}
        assert names == {"PL A"}

        # selected_only=false returns both
        r = await ac.get("/api/v1/playlists/stats?selected_only=false")
        assert r.status_code == 200
        data = r.json()
        names = {it["name"] for it in data if it.get("playlist_id") is not None}
        assert names == {"PL A", "PL B"}
