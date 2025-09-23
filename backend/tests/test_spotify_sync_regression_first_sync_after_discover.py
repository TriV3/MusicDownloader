import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_first_sync_not_skipped_when_snapshot_already_persisted(monkeypatch):
    """Regression: If discovery persisted snapshot before any sync, the first sync must not skip.

    Flow:
    - Discover persists playlist with snapshot (simulate /me/playlists and playlist metadata).
    - Sync should ingest tracks even if snapshot matches, because there are no existing links yet.
    """
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Fake Spotify API
    async def fake_spotify_get(self, url, headers=None, **kwargs):  # type: ignore
        class Resp:
            status_code = 200

            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

            @property
            def text(self):
                return "ok"

        u = str(url)
        if u.startswith("https://api.spotify.com/v1/me/playlists"):
            # Discovery returns one playlist with snapshot
            return Resp({
                "items": [
                    {
                        "id": "plX",
                        "name": "TestList",
                        "description": None,
                        "owner": {"id": "me"},
                        "snapshot_id": "snap0",
                    },
                ],
                "next": None,
            })
        if u.endswith("?fields=snapshot_id"):
            return Resp({"snapshot_id": "snap0"})
        if "/playlists/plX/tracks" in u:
            return Resp({
                "items": [
                    {
                        "added_at": "2024-01-02T03:04:05Z",
                        "track": {
                            "id": "trkZ",
                            "name": "Hello",
                            "artists": [{"name": "World"}],
                            "album": {"name": "Album Z", "images": []},
                            "duration_ms": 100000,
                            "external_ids": {},
                            "explicit": False,
                        },
                    },
                ],
                "next": None,
            })
        return Resp({"items": [], "next": None})

    import httpx as _httpx
    _orig_get = _httpx.AsyncClient.get

    async def selective_get(self, url, headers=None, **kwargs):  # type: ignore
        url_str = str(url)
        if url_str.startswith("https://api.spotify.com/"):
            return await fake_spotify_get(self, url, headers=headers, **kwargs)
        return await _orig_get(self, url, headers=headers, **kwargs)

    monkeypatch.setattr(_httpx.AsyncClient, "get", selective_get, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create account & token
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "acc_reg", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]
        r = await ac.post("/api/v1/oauth/tokens", json={"source_account_id": acc_id, "provider": "spotify", "access_token": "AT"})
        assert r.status_code == 200

        # Discover with persist=true to store playlist with snapshot
        r = await ac.get(f"/api/v1/playlists/spotify/discover?account_id={acc_id}&persist=true")
        assert r.status_code == 200
        discovered = r.json()
        assert discovered and discovered[0]["provider_playlist_id"] == "plX"
        # Select playlist
        r = await ac.post("/api/v1/playlists/spotify/select", json={"account_id": acc_id, "playlist_ids": ["plX"]})
        assert r.status_code == 200

        # Now run sync: despite snapshot matching, there are no links yet, so it should NOT be skipped
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        assert summary["total_tracks_created"] == 1
        assert summary["total_links_created"] == 1
        assert summary["playlists"][0]["skipped"] is False
