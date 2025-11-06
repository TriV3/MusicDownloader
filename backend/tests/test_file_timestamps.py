import os
import asyncio
from datetime import datetime
from pathlib import Path
from httpx import AsyncClient
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")
os.environ.setdefault("DOWNLOAD_FAKE", "1")

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


async def _create_youtube_candidate(ac: AsyncClient, track_id: int):
    r = await ac.post("/api/v1/candidates/", json={
        "track_id": track_id,
        "provider": "youtube",
        "external_id": "fake_youtube_id",
        "url": "https://youtube.com/watch?v=fake",
        "title": "Fake YouTube Video",
        "channel": "Fake Channel",
        "duration_sec": 180,
        "score": 0.9,
        "chosen": True,
    })
    assert r.status_code == 200
    return r.json()["id"]


@pytest.mark.asyncio
async def test_download_file_timestamps_with_release_and_playlist_dates(tmp_path, monkeypatch):
    """Test that downloaded files have correct timestamps based on release_date and added_at."""
    
    # Set up secret key and temporary directory
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    
    # Mock Spotify API calls
    async def fake_spotify_get(self, url, headers=None, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                u = str(url)
                if "/playlists" in u and "/tracks" not in u:
                    return {
                        "id": "test_playlist_456",
                        "snapshot_id": "snapshot_def",
                        "name": "Test Download Playlist",
                    }
                elif "/playlists/test_playlist_456/tracks" in u:
                    return {
                        "items": [
                            {
                                "added_at": "2024-06-10T12:00:00Z",  # Added to playlist in June 2024
                                "track": {
                                    "id": "download_test_track",
                                    "name": "Download Test Song",
                                    "artists": [{"name": "Test Artist"}],
                                    "album": {
                                        "name": "Test Album",
                                        "images": [{"url": "http://img/test", "width": 300}],
                                        "release_date": "2023-03-20",  # Released in March 2023
                                        "release_date_precision": "day"
                                    },
                                    "duration_ms": 200000,
                                    "external_ids": {"isrc": "TESTDOWNLOAD1"},
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
        # Create Spotify account and OAuth token
        account_id = await _create_spotify_account(ac)
        r = await ac.post("/api/v1/oauth/tokens", json={
            "source_account_id": account_id,
            "provider": "spotify",
            "access_token": "fake_token",
        })
        assert r.status_code == 200

        # Create playlist and sync
        r = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "provider_playlist_id": "test_playlist_456",
            "name": "Test Download Playlist",
            "source_account_id": account_id,
            "selected": True,
        })
        assert r.status_code == 200

        # Sync to create track with release_date and playlist added_at
        r = await ac.post(f"/api/v1/playlists/spotify/sync?account_id={account_id}")
        assert r.status_code == 200
        sync_result = r.json()
        assert sync_result["total_tracks_created"] == 1

        # Get the created track
        try:
            from backend.app.db.session import async_session  # type: ignore
            from backend.app.db.models.models import Track, PlaylistTrack  # type: ignore
            from sqlalchemy import select  # type: ignore
        except Exception:  # pragma: no cover
            from app.db.session import async_session  # type: ignore
            from app.db.models.models import Track, PlaylistTrack  # type: ignore
            from sqlalchemy import select  # type: ignore

        async with async_session() as s:
            # Get the track we just created by looking for the specific test data
            result = await s.execute(
                select(Track).where(Track.title == "Download Test Song")
            )
            track = result.scalars().first()
            assert track is not None, "Test track not found"
            track_id = track.id
            
            # Verify dates are stored correctly
            assert track.release_date is not None
            assert track.release_date.year == 2023
            assert track.release_date.month == 3
            assert track.release_date.day == 20
            
            result = await s.execute(select(PlaylistTrack).where(PlaylistTrack.track_id == track_id))
            playlist_track = result.scalars().first()
            assert playlist_track is not None
            assert playlist_track.added_at is not None
            assert playlist_track.added_at.year == 2024
            assert playlist_track.added_at.month == 6
            assert playlist_track.added_at.day == 10

        # Create YouTube candidate for download
        candidate_id = await _create_youtube_candidate(ac, track_id)

        # Start download worker
        r = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert r.status_code == 200

        # Enqueue download
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={track_id}&candidate_id={candidate_id}")
        assert r.status_code == 200
        download_id = r.json()["id"]

        # Wait for download to complete
        r = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 5.0, "track_id": track_id, "stop_after": True})
        assert r.status_code == 200

        # Get download information directly from DB since API seems to have session issues in tests
        async with async_session() as s:
            from sqlalchemy import select
            try:
                from backend.app.db.models.models import Download
            except Exception:
                from app.db.models.models import Download
            result = await s.execute(select(Download).where(Download.id == download_id))
            download = result.scalars().first()
            
            assert download is not None, f"Download {download_id} not found in database"
            assert download.status.value == "done", f"Download status is {download.status}, expected 'done'"
            assert download.filepath is not None, "Download filepath is None"
            
            print(f"Download completed: {download.filepath}")
            
            # Check that file exists and has correct timestamps
            file_path = Path(download.filepath)
            assert file_path.exists(), f"Downloaded file does not exist: {download.filepath}"
            
            # Get file timestamps
            stat = file_path.stat()
            file_creation_time = datetime.fromtimestamp(stat.st_ctime)
            file_modification_time = datetime.fromtimestamp(stat.st_mtime)
            
            print(f"File creation time: {file_creation_time}")
            print(f"File modification time: {file_modification_time}")
            
            # Get track and playlist data for comparison
            result = await s.execute(select(Track).where(Track.id == track_id))
            track = result.scalars().first()
            assert track is not None
            assert track.release_date is not None
            
            result = await s.execute(select(PlaylistTrack).where(PlaylistTrack.track_id == track_id))
            playlist_track = result.scalars().first()
            assert playlist_track is not None
            assert playlist_track.added_at is not None
            
            print(f"Track release date: {track.release_date}")
            print(f"Playlist added at: {playlist_track.added_at}")
            
            # Verify timestamps match expected dates (allowing for some tolerance)
            # File creation time should match release date
            expected_creation = track.release_date.replace(hour=0, minute=0, second=0, microsecond=0)
            actual_creation = file_creation_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # File modification time should match playlist added_at
            expected_modification = playlist_track.added_at.replace(microsecond=0)
            actual_modification = file_modification_time.replace(microsecond=0)
            
            print(f"Expected creation (release): {expected_creation}")
            print(f"Actual creation: {actual_creation}")
            print(f"Expected modification (added): {expected_modification}")
            print(f"Actual modification: {actual_modification}")
            
            # Check dates match (allowing some tolerance for time precision)
            creation_diff = abs((expected_creation - actual_creation).total_seconds())
            modification_diff = abs((expected_modification - actual_modification).total_seconds())
            
            assert creation_diff < 86400, f"Creation time mismatch: expected {expected_creation}, got {actual_creation}"
            assert modification_diff < 3600, f"Modification time mismatch: expected {expected_modification}, got {actual_modification}"
            
            print("✅ File timestamps are correctly set!")
            print(f"   Creation time matches release date: {expected_creation}")
            print(f"   Modification time matches playlist addition: {expected_modification}")
        
        # Note: On some systems, setting file creation time might not work perfectly
        # So we mainly verify that modification time is set to the playlist added_at date
        # The modification time should be close to the playlist added_at (2024-06-10)
        expected_mod_time = playlist_track.added_at.replace(tzinfo=None)  # Remove timezone for comparison
        
        # Allow some tolerance (within 1 day) since timestamp setting might have precision issues
        time_diff = abs((file_modification_time - expected_mod_time).total_seconds())
        assert time_diff < 86400, f"Modification time {file_modification_time} too far from expected {expected_mod_time}"
        
        print("✅ File timestamps test passed!")