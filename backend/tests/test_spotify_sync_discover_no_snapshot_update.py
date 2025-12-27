"""
Test that Spotify discover does NOT update the snapshot on existing playlists.
This ensures that sync can detect changes properly.
"""
import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_discover_does_not_update_snapshot_on_existing_playlist(monkeypatch):
    """
    Regression test: Discover with persist=true should NOT update the snapshot
    on existing playlists. Only sync should update the snapshot after successfully
    ingesting tracks. This ensures new tracks are detected on subsequent syncs.
    
    Flow:
    1. Discover persists playlist with snapshot "snap1"
    2. First sync ingests tracks and stores snapshot "snap1"
    3. User adds a track on Spotify (snapshot changes to "snap2")
    4. Discover runs again (should NOT update local snapshot)
    5. Sync should detect the change and ingest the new track
    """
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Track which snapshot to return (simulate Spotify changing)
    current_snapshot = {"value": "snap1"}
    track_items = {"items": [
        {
            "added_at": "2024-01-02T03:04:05Z",
            "track": {
                "id": "trk1",
                "name": "First Song",
                "artists": [{"name": "Artist A"}],
                "album": {"name": "Album 1", "images": []},
                "duration_ms": 180000,
                "external_ids": {},
                "explicit": False,
            },
        },
    ]}

    async def fake_spotify_get(self, url, headers=None, **kwargs):
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
            return Resp({
                "items": [
                    {
                        "id": "plTest",
                        "name": "Test Playlist",
                        "description": None,
                        "owner": {"id": "testuser"},
                        "snapshot_id": current_snapshot["value"],
                    },
                ],
                "next": None,
            })
        if u.endswith("?fields=snapshot_id"):
            return Resp({"snapshot_id": current_snapshot["value"]})
        if "/playlists/plTest/tracks" in u:
            return Resp(track_items)
        return Resp({"items": [], "next": None})

    import httpx as _httpx
    _orig_get = _httpx.AsyncClient.get

    async def selective_get(self, url, headers=None, **kwargs):
        url_str = str(url)
        if url_str.startswith("https://api.spotify.com/"):
            return await fake_spotify_get(self, url, headers=headers, **kwargs)
        return await _orig_get(self, url, headers=headers, **kwargs)

    monkeypatch.setattr(_httpx.AsyncClient, "get", selective_get, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create account & token
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "test_acc", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]
        r = await ac.post("/api/v1/oauth/tokens", json={"source_account_id": acc_id, "provider": "spotify", "access_token": "AT"})
        assert r.status_code == 200

        # Step 1: First discover persists playlist with snapshot "snap1"
        r = await ac.get(f"/api/v1/playlists/spotify/discover?account_id={acc_id}&persist=true")
        assert r.status_code == 200
        discovered = r.json()
        assert len(discovered) == 1
        assert discovered[0]["provider_playlist_id"] == "plTest"
        assert discovered[0]["snapshot"] == "snap1"  # Initial snapshot saved

        # Select the playlist
        r = await ac.post("/api/v1/playlists/spotify/select", json={"account_id": acc_id, "playlist_ids": ["plTest"]})
        assert r.status_code == 200

        # Step 2: First sync
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        assert summary["total_tracks_created"] == 1
        assert summary["total_links_created"] == 1

        # Step 3: Simulate Spotify change - add a new track
        current_snapshot["value"] = "snap2"
        track_items["items"].append({
            "added_at": "2024-01-03T10:00:00Z",
            "track": {
                "id": "trk2",
                "name": "Second Song",
                "artists": [{"name": "Artist B"}],
                "album": {"name": "Album 2", "images": []},
                "duration_ms": 200000,
                "external_ids": {},
                "explicit": False,
            },
        })

        # Step 4: Discover again - should NOT update local snapshot
        r = await ac.get(f"/api/v1/playlists/spotify/discover?account_id={acc_id}&persist=true")
        assert r.status_code == 200
        discovered = r.json()
        # The snapshot shown may be the remote one in the response, but stored value should be unchanged
        # Let's verify by checking the sync behavior

        # Step 5: Sync should detect the change and ingest new track
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        
        # Should have created the new track
        assert summary["total_tracks_created"] == 1, f"Expected 1 new track, got {summary}"
        assert summary["total_links_created"] == 1, f"Expected 1 new link, got {summary}"
        assert summary["playlists"][0]["skipped"] is False, "Playlist should NOT be skipped"


@pytest.mark.asyncio
async def test_sync_force_bypasses_snapshot_check(monkeypatch):
    """
    Test that force=true parameter bypasses the snapshot check
    and performs a full sync even when snapshots match.
    """
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    async def fake_spotify_get(self, url, headers=None, **kwargs):
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
            return Resp({
                "items": [{"id": "plForce", "name": "Force Test", "owner": {"id": "me"}, "snapshot_id": "snapF"}],
                "next": None,
            })
        if u.endswith("?fields=snapshot_id"):
            return Resp({"snapshot_id": "snapF"})
        if "/playlists/plForce/tracks" in u:
            return Resp({
                "items": [{
                    "added_at": "2024-01-01T00:00:00Z",
                    "track": {
                        "id": "trkF",
                        "name": "Force Track",
                        "artists": [{"name": "Force Artist"}],
                        "album": {"name": "Force Album", "images": []},
                        "duration_ms": 150000,
                        "external_ids": {},
                        "explicit": False,
                    },
                }],
                "next": None,
            })
        return Resp({"items": [], "next": None})

    import httpx as _httpx
    _orig_get = _httpx.AsyncClient.get

    async def selective_get(self, url, headers=None, **kwargs):
        url_str = str(url)
        if url_str.startswith("https://api.spotify.com/"):
            return await fake_spotify_get(self, url, headers=headers, **kwargs)
        return await _orig_get(self, url, headers=headers, **kwargs)

    monkeypatch.setattr(_httpx.AsyncClient, "get", selective_get, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Setup account
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "force_acc", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]
        r = await ac.post("/api/v1/oauth/tokens", json={"source_account_id": acc_id, "provider": "spotify", "access_token": "AT"})
        assert r.status_code == 200

        # Discover and select playlist
        r = await ac.get(f"/api/v1/playlists/spotify/discover?account_id={acc_id}&persist=true")
        assert r.status_code == 200
        r = await ac.post("/api/v1/playlists/spotify/select", json={"account_id": acc_id, "playlist_ids": ["plForce"]})
        assert r.status_code == 200

        # First sync
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        assert summary["total_tracks_created"] == 1

        # Second sync without force - should be skipped (snapshot unchanged)
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        summary = r.json()
        assert summary["playlists"][0]["skipped"] is True

        # Third sync with force=true - should NOT be skipped
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}&force=true")
        assert r.status_code == 200
        summary = r.json()
        assert summary["playlists"][0]["skipped"] is False
        # No new tracks created (already exist)
        assert summary["total_tracks_created"] == 0
        # But sync was performed (not skipped)
        assert summary["playlists"][0]["tracks_created"] == 0
