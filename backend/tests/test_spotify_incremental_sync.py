import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


@pytest.mark.asyncio
async def test_spotify_incremental_sync(monkeypatch):
    """Validate incremental sync behaviour:
    - Initial sync ingests 2 tracks.
    - Second sync with same snapshot is skipped.
    - Third sync with new snapshot adds one track and removes one.
    """
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # State machine for fake playlist contents
    state = {"phase": 0}

    def playlist_tracks_payload():
        if state["phase"] == 0:
            # Initial two tracks
            return {
                "items": [
                    {
                        "added_at": "2024-01-02T03:04:05Z",
                        "track": {
                            "id": "trkA",
                            "name": "Song Alpha",
                            "artists": [{"name": "Artist One"}],
                            "album": {"name": "Album One", "images": []},
                            "duration_ms": 111000,
                            "external_ids": {"isrc": "ISO1"},
                            "explicit": False,
                        },
                    },
                    {
                        "added_at": None,
                        "track": {
                            "id": "trkB",
                            "name": "Song Beta",
                            "artists": [{"name": "Artist Two"}],
                            "album": {"name": "Album Two", "images": []},
                            "duration_ms": 222000,
                            "external_ids": {},
                            "explicit": False,
                        },
                    },
                ],
                "next": None,
            }
        elif state["phase"] == 2:
            # Remove trkB, add trkC
            return {
                "items": [
                    {
                        "added_at": "2024-01-02T03:04:05Z",
                        "track": {
                            "id": "trkA",
                            "name": "Song Alpha",
                            "artists": [{"name": "Artist One"}],
                            "album": {"name": "Album One", "images": []},
                            "duration_ms": 111000,
                            "external_ids": {"isrc": "ISO1"},
                            "explicit": False,
                        },
                    },
                    {
                        "added_at": None,
                        "track": {
                            "id": "trkC",
                            "name": "Song Gamma",
                            "artists": [{"name": "Artist Three"}],
                            "album": {"name": "Album Three", "images": []},
                            "duration_ms": 333000,
                            "external_ids": {},
                            "explicit": False,
                        },
                    },
                ],
                "next": None,
            }
        else:  # phase 1 skip path should not fetch tracks logically, but if it does return same list
            return playlist_tracks_payload()

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
        if u.endswith("?fields=snapshot_id"):
            # Return snapshot depending on phase
            if state["phase"] == 0:
                snap = {"snapshot_id": "snap_initial"}
            elif state["phase"] == 1:
                snap = {"snapshot_id": "snap_initial"}  # unchanged
            else:
                snap = {"snapshot_id": "snap_changed"}
            return Resp(snap)
        if "/playlists/plIncr/tracks" in u:
            return Resp(playlist_tracks_payload())
        return Resp({"items": [], "next": None})

    import httpx as _httpx
    monkeypatch.setattr(_httpx.AsyncClient, "get", fake_spotify_get, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create account & token
        r = await ac.post("/api/v1/sources/accounts", json={"type": "spotify", "name": "acc_inc", "enabled": True})
        assert r.status_code == 200
        acc_id = r.json()["id"]
        r = await ac.post(
            "/api/v1/oauth/tokens",
            json={"source_account_id": acc_id, "provider": "spotify", "access_token": "AT"},
        )
        assert r.status_code == 200

        # Create playlist marked selected
        r = await ac.post(
            "/api/v1/playlists/",
            json={
                "provider": "spotify",
                "name": "Incremental",
                "source_account_id": acc_id,
                "provider_playlist_id": "plIncr",
                "selected": True,
            },
        )
        assert r.status_code == 200

        # Phase 0: initial sync
        state["phase"] = 0
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["total_tracks_created"] == 2
        assert data["total_links_created"] == 2
        # snapshot should now be stored

        # Phase 1: snapshot unchanged -> skipped
        state["phase"] = 1
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        skipped = r.json()
        # No new creations or links (skipped)
        assert skipped["total_tracks_created"] == 0
        assert skipped["total_links_created"] == 0
        assert skipped["playlists"][0]["skipped"] is True

        # Phase 2: changed snapshot -> removal + addition
        state["phase"] = 2
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={acc_id}")
        assert r.status_code == 200
        changed = r.json()
        # One new track (trkC), one removed (trkB)
        assert changed["total_tracks_created"] == 1
        assert changed["total_links_removed"] == 1
        playlist_summary = changed["playlists"][0]
        assert playlist_summary["links_removed"] == 1
        assert playlist_summary["tracks_created"] == 1
        assert playlist_summary["skipped"] is False

    # Cleanup
    try:
        from backend.app.db.session import async_session  # type: ignore
        from backend.app.db.models.models import OAuthToken, Playlist, SourceAccount, Track, TrackIdentity, PlaylistTrack  # type: ignore
    except Exception:  # pragma: no cover
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
