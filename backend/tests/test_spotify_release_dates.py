import os
import asyncio
from datetime import datetime
from httpx import AsyncClient
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_spotify_account(ac: AsyncClient):
    r = await ac.post("/api/v1/sources/accounts", json={
        "type": "spotify",
        "name": "Test Spotify Account",
        "enabled": True
    })
    assert r.status_code == 200
    return r.json()["id"]


@pytest.mark.asyncio
async def test_spotify_sync_with_release_dates(monkeypatch):
    """Test that Spotify sync properly extracts and stores release dates from album data."""
    
    # Set up secret key for token encryption
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Mock httpx.AsyncClient.get for Spotify API calls
    original_get = None
    async def fake_spotify_get(self, url, headers=None, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                u = str(url)
                if "/playlists" in u and "/tracks" not in u:
                    # Playlist metadata request
                    return {
                        "id": "test_playlist_123",
                        "snapshot_id": "snapshot_abc",
                        "name": "Test Release Dates Playlist",
                    }
                elif "/playlists/test_playlist_123/tracks" in u:
                    # Playlist tracks request with album release date info
                    return {
                        "items": [
                            {
                                "added_at": "2024-02-15T10:30:00Z",
                                "track": {
                                    "id": "track_with_full_date",
                                    "name": "Song with Full Release Date",
                                    "artists": [{"name": "Artist One"}],
                                    "album": {
                                        "name": "Album 2023",
                                        "images": [{"url": "http://img/1", "width": 300}],
                                        "release_date": "2023-06-15",
                                        "release_date_precision": "day"
                                    },
                                    "duration_ms": 180000,
                                    "external_ids": {"isrc": "TEST123456789"},
                                    "explicit": False,
                                },
                            },
                            {
                                "added_at": "2024-03-01T14:20:00Z",
                                "track": {
                                    "id": "track_with_year_only",
                                    "name": "Song with Year Only",
                                    "artists": [{"name": "Artist Two"}],
                                    "album": {
                                        "name": "Old Album",
                                        "images": [],
                                        "release_date": "2020",
                                        "release_date_precision": "year"
                                    },
                                    "duration_ms": 240000,
                                    "external_ids": {},
                                    "explicit": True,
                                },
                            },
                            {
                                "added_at": "2024-01-10T08:15:00Z",
                                "track": {
                                    "id": "track_with_month_precision",
                                    "name": "Song with Month Precision",
                                    "artists": [{"name": "Artist Three"}],
                                    "album": {
                                        "name": "Monthly Album",
                                        "images": [{"url": "http://img/2", "width": 640}],
                                        "release_date": "2022-12",
                                        "release_date_precision": "month"
                                    },
                                    "duration_ms": 195000,
                                    "external_ids": {"isrc": "MONTH123456"},
                                    "explicit": False,
                                },
                            },
                        ],
                        "next": None
                    }
                return {}
        return Resp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_spotify_get)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create Spotify account
        account_id = await _create_spotify_account(ac)

        # Create OAuth token
        r = await ac.post("/api/v1/oauth/tokens", json={
            "source_account_id": account_id,
            "provider": "spotify",
            "access_token": "fake_token",
        })
        assert r.status_code == 200

        # Create playlist linked to the account
        r = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "provider_playlist_id": "test_playlist_123",
            "name": "Test Release Dates Playlist",
            "source_account_id": account_id,
            "selected": True,
        })
        assert r.status_code == 200

        # Sync playlists
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={account_id}")
        assert r.status_code == 200
        sync_result = r.json()
        
        # Debug: print the actual result
        print(f"Sync result: {sync_result}")
        
        # Should have created 3 tracks
        assert sync_result["total_tracks_created"] == 3

        # Verify tracks were created by checking the database directly
        try:
            from backend.app.db.session import async_session  # type: ignore
            from backend.app.db.models.models import Track  # type: ignore
            from sqlalchemy import select  # type: ignore
        except Exception:  # pragma: no cover
            from app.db.session import async_session  # type: ignore
            from app.db.models.models import Track  # type: ignore
            from sqlalchemy import select  # type: ignore

        async with async_session() as s:
            result = await s.execute(select(Track))
            tracks = result.scalars().all()
            
            # Debug: print tracks from database
            print(f"Found {len(tracks)} tracks in database:")
            for t in tracks:
                print(f"  - {t.title} by {t.artists} (release_date: {t.release_date})")
            
            # Find tracks by title
            track_full_date = next((t for t in tracks if t.title == "Song with Full Release Date"), None)
            track_year_only = next((t for t in tracks if t.title == "Song with Year Only"), None)
            track_month_precision = next((t for t in tracks if t.title == "Song with Month Precision"), None)
        
        assert track_full_date is not None
        assert track_year_only is not None
        assert track_month_precision is not None
        
        # Check release dates are properly parsed
        # Full date: 2023-06-15
        assert track_full_date.release_date is not None
        assert track_full_date.release_date.year == 2023
        assert track_full_date.release_date.month == 6
        assert track_full_date.release_date.day == 15
        
        # Year only: 2020 -> should become 2020-01-01
        assert track_year_only.release_date is not None
        assert track_year_only.release_date.year == 2020
        assert track_year_only.release_date.month == 1
        assert track_year_only.release_date.day == 1
        
        # Month precision: 2022-12 -> should become 2022-12-01
        assert track_month_precision.release_date is not None
        assert track_month_precision.release_date.year == 2022
        assert track_month_precision.release_date.month == 12
        assert track_month_precision.release_date.day == 1

        # Check playlist entries have proper added_at dates
        # We access PlaylistTrack directly from database
        try:
            from backend.app.db.models.models import PlaylistTrack  # type: ignore
        except Exception:  # pragma: no cover
            from app.db.models.models import PlaylistTrack  # type: ignore

        async with async_session() as s:
            result = await s.execute(select(PlaylistTrack).where(PlaylistTrack.playlist_id == 1))
            entries = result.scalars().all()
            assert len(entries) == 3
            
            # Check that added_at dates are preserved (find by track_id)
            entry_full_date = next((e for e in entries if e.track_id == track_full_date.id), None)
            assert entry_full_date is not None
            assert entry_full_date.added_at is not None
            assert entry_full_date.added_at.year == 2024
            assert entry_full_date.added_at.month == 2
            assert entry_full_date.added_at.day == 15