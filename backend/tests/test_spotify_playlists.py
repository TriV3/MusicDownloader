import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_spotify_playlists_discover_and_select(monkeypatch):
    # Basic env
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Fake Spotify API for playlists
    async def fake_spotify_get(self, url, headers=None, **kwargs):  # type: ignore
        class Resp:
            status_code = 200

            def json(self):
                return {
                    "items": [
                        {
                            "id": "pl1",
                            "name": "Morning Mix",
                            "description": "Great tracks",
                            "owner": {"display_name": "Tester", "id": "tester"},
                            "snapshot_id": "snap1",
                        },
                        {
                            "id": "pl2",
                            "name": "Club Bangers",
                            "description": None,
                            "owner": {"id": "tester"},
                            "snapshot_id": "snap2",
                        },
                    ],
                    "next": None,
                }

            @property
            def text(self):
                return "ok"

        return Resp()

    import httpx as _httpx
    _orig_get = _httpx.AsyncClient.get

    async def selective_get(self, url, headers=None, **kwargs):  # type: ignore
        url_str = str(url)
        if url_str.startswith("https://api.spotify.com/"):
            return await fake_spotify_get(self, url, headers=headers, **kwargs)
        return await _orig_get(self, url, headers=headers, **kwargs)

    monkeypatch.setattr(_httpx.AsyncClient, "get", selective_get, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create a Spotify account (use a unique name to avoid collisions across tests)
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "acc_pl", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]

        # Store an OAuth token (access token only is sufficient for this test)
        r = await ac.post(
            "/api/v1/oauth/tokens",
            json={
                "source_account_id": acc_id,
                "provider": "spotify",
                "access_token": "AT",
            },
        )
        assert r.status_code == 200

        # Discover (persist = true)
        r = await ac.get(f"/api/v1/playlists/spotify/discover?account_id={acc_id}&persist=true")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) == 2
        ids = sorted([p["provider_playlist_id"] for p in data])
        assert ids == ["pl1", "pl2"]

        # Check persisted rows
        r = await ac.get(f"/api/v1/playlists/?provider=spotify&account_id={acc_id}")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        assert all(p.get("selected") in (False, None) for p in rows)

        # Select one playlist
        r = await ac.post("/api/v1/playlists/spotify/select", json={"account_id": acc_id, "playlist_ids": ["pl2"]})
        assert r.status_code == 200

        # Selected filter should return only pl2
        r = await ac.get(f"/api/v1/playlists/?provider=spotify&account_id={acc_id}&selected=true")
        assert r.status_code == 200
        selected = r.json()
        assert len(selected) == 1
        assert selected[0]["provider_playlist_id"] == "pl2"
        assert selected[0]["selected"] is True

    # Cleanup to avoid leaking state to other tests using shared in-memory DB
    try:
        from backend.app.db.session import async_session  # type: ignore
        from backend.app.db.models.models import OAuthToken, Playlist, SourceAccount  # type: ignore
    except Exception:
        from app.db.session import async_session  # type: ignore
        from app.db.models.models import OAuthToken, Playlist, SourceAccount  # type: ignore

    from sqlalchemy import delete
    async with async_session() as s:
        await s.execute(delete(OAuthToken))
        await s.execute(delete(Playlist))
        await s.execute(delete(SourceAccount))
        await s.commit()