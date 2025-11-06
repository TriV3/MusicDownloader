"""Test playlist entries endpoint returns correct data structure."""
import pytest
from httpx import AsyncClient

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_playlist_entries_includes_added_at():
    """Test that playlist entries include added_at field for each track."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # First, create a source account
        source_resp = await ac.post("/api/v1/sources/accounts", json={
            "type": "spotify",
            "name": "test_user",
            "enabled": True
        })
        assert source_resp.status_code == 200
        source = source_resp.json()
        
        # Create a playlist
        playlist_resp = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "provider_id": "test_playlist",
            "name": "Test Playlist",
            "owner": "test_owner",
            "account_id": source["id"],
            "selected": True
        })
        assert playlist_resp.status_code == 200
        playlist = playlist_resp.json()
        
        # Create a track
        track_resp = await ac.post("/api/v1/tracks/", json={
            "artists": "Test Artist",
            "title": "Test Track"
        })
        assert track_resp.status_code == 200
        track = track_resp.json()
        
        # Add track to playlist
        link_resp = await ac.post(
            "/api/v1/playlist_tracks/",
            json={
                "playlist_id": playlist["id"],
                "track_id": track["id"],
                "position": 1
            }
        )
        assert link_resp.status_code == 200
        
        # Get playlist entries
        entries_resp = await ac.get(f"/api/v1/playlists/{playlist['id']}/entries")
        assert entries_resp.status_code == 200
        entries = entries_resp.json()
        
        # Verify structure
        assert isinstance(entries, list)
        assert len(entries) == 1
        
        entry = entries[0]
        assert "position" in entry
        assert "added_at" in entry
        assert "track" in entry
        
        # Verify track structure
        assert entry["track"]["id"] == track["id"]
        assert entry["track"]["artists"] == "Test Artist"
        assert entry["track"]["title"] == "Test Track"
        
        # Verify position
        assert entry["position"] == 1
        
        # Verify added_at is present (can be None initially)
        assert "added_at" in entry


@pytest.mark.asyncio
async def test_playlist_entries_ordered_by_position():
    """Test that playlist entries are ordered by position."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create source and playlist
        source_resp = await ac.post("/api/v1/sources/accounts", json={
            "type": "spotify",
            "name": "test_user2",
            "enabled": True
        })
        source = source_resp.json()
        
        playlist_resp = await ac.post("/api/v1/playlists/", json={
            "provider": "spotify",
            "provider_id": "test_playlist2",
            "name": "Test Playlist 2",
            "owner": "test_owner",
            "account_id": source["id"],
            "selected": True
        })
        playlist = playlist_resp.json()
        
        # Create multiple tracks
        tracks = []
        for i in range(3):
            track_resp = await ac.post("/api/v1/tracks/", json={
                "artists": f"Artist {i}",
                "title": f"Track {i}"
            })
            tracks.append(track_resp.json())
        
        # Add tracks in reverse order (position 3, 2, 1)
        for i, track in enumerate(tracks):
            await ac.post(
                "/api/v1/playlist_tracks/",
                json={
                    "playlist_id": playlist["id"],
                    "track_id": track["id"],
                    "position": 3 - i
                }
            )
        
        # Get entries
        entries_resp = await ac.get(f"/api/v1/playlists/{playlist['id']}/entries")
        entries = entries_resp.json()
        
        # Verify order (should be sorted by position: 1, 2, 3)
        assert len(entries) == 3
        assert entries[0]["position"] == 1
        assert entries[1]["position"] == 2
        assert entries[2]["position"] == 3
        
        # Verify corresponding tracks
        assert entries[0]["track"]["title"] == "Track 2"
        assert entries[1]["track"]["title"] == "Track 1"
        assert entries[2]["track"]["title"] == "Track 0"
