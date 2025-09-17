import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_spotify_sync_selected_playlists(monkeypatch):
    # Basic env
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Fake Spotify API for playlist tracks
    async def fake_spotify_get(self, url, headers=None, **kwargs):  # type: ignore
        class Resp:
            status_code = 200

            def json(self):
                u = str(url)
                if "/playlists/plA/tracks" in u:
                    return {
                        "items": [
                            {
                                "added_at": "2024-01-02T03:04:05Z",
                                "track": {
                                    "id": "trk1",
                                    "name": "Espresso",
                                    "artists": [{"name": "Sabrina Carpenter"}],
                                    "album": {"name": "Emails I Can't Send", "images": [{"url": "http://img/1", "width": 64}, {"url": "http://img/2", "width": 300}]},
                                    "duration_ms": 176000,
                                    "external_ids": {"isrc": "USUG12201234"},
                                    "explicit": False,
                                },
                            },
                            {
                                "added_at": None,
                                "track": {
                                    "id": "trk2",
                                    "name": "Quand La Musique Est Bonne",
                                    "artists": [{"name": "Jean-Jacques Goldman"}],
                                    "album": {"name": "Goldman", "images": []},
                                    "duration_ms": 234000,
                                    "external_ids": {},
                                    "explicit": False,
                                },
                            },
                        ],
                        "next": None,
                    }
                return {"items": [], "next": None}

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
        # Create account
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "acc_sync", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]

        # Token
        r = await ac.post(
            "/api/v1/oauth/tokens",
            json={
                "source_account_id": acc_id,
                "provider": "spotify",
                "access_token": "AT",
            },
        )
        assert r.status_code == 200

        # Create and select playlist plA
        r = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "name": "PL A",
            "source_account_id": acc_id,
            "provider_playlist_id": "plA",
            "selected": True,
        })
        assert r.status_code == 200

        # First sync
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        assert summary["total_tracks_created"] == 2
        assert summary["total_links_created"] == 2

        # Second sync should be idempotent (no new creates)
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary2 = r.json()
        assert summary2["total_tracks_created"] == 0
        # Links also should not duplicate
        assert summary2["total_links_created"] == 0
    # Cleanup DB (shared in-memory across test session)
    try:
        from backend.app.db.session import async_session  # type: ignore
        from backend.app.db.models.models import OAuthToken, Playlist, SourceAccount, Track, TrackIdentity, PlaylistTrack  # type: ignore
    except Exception:
        from app.db.session import async_session  # type: ignore
        from app.db.models.models import OAuthToken, Playlist, SourceAccount, Track, TrackIdentity, PlaylistTrack  # type: ignore

    from sqlalchemy import delete
    async with async_session() as s:
        await s.execute(delete(PlaylistTrack))
        await s.execute(delete(TrackIdentity))
        await s.execute(delete(OAuthToken))
        await s.execute(delete(Playlist))
        await s.execute(delete(Track))
        await s.execute(delete(SourceAccount))
        await s.commit()
