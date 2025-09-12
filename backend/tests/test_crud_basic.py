import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_sources_accounts_crud():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # empty list
        r = await ac.get("/api/v1/sources/accounts")
        assert r.status_code == 200
        assert r.json() == []

        # create
        r = await ac.post(
            "/api/v1/sources/accounts",
            json={"type": "spotify", "name": "acc1", "enabled": True},
        )
        assert r.status_code == 200
        acc = r.json()
        assert acc["id"] >= 1
        assert acc["type"] == "spotify"

        # get
        r = await ac.get(f"/api/v1/sources/accounts/{acc['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "acc1"


@pytest.mark.asyncio
async def test_playlists_crud():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Ensure account exists
        await ac.post(
            "/api/v1/sources/accounts",
            json={"type": "spotify", "name": "acc2", "enabled": True},
        )
        # list
        r = await ac.get("/api/v1/playlists/")
        assert r.status_code == 200
        # create
        r = await ac.post(
            "/api/v1/playlists/",
            json={"provider": "spotify", "name": "P1", "source_account_id": 1},
        )
        assert r.status_code == 200
        pid = r.json()["id"]
        # get
        r = await ac.get(f"/api/v1/playlists/{pid}")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_tracks_crud():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/tracks/",
            json={
                "title": "Song",
                "artists": "Artist",
                "normalized_title": "song",
                "normalized_artists": "artist",
            },
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        r = await ac.get(f"/api/v1/tracks/{tid}")
        assert r.status_code == 200
        # delete track
        r = await ac.delete(f"/api/v1/tracks/{tid}")
        assert r.status_code == 204
        # ensure gone
        r = await ac.get(f"/api/v1/tracks/{tid}")
        assert r.status_code == 404