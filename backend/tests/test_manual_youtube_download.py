import os
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
import json

os.environ.setdefault("YOUTUBE_SEARCH_FAKE", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Test Song", artists="Artist", duration_ms=180000):
    """Helper to create a track for testing."""
    r = await ac.post(
        "/api/v1/tracks/",
        json={
            "title": title,
            "artists": artists,
            "duration_ms": duration_ms,
            "normalized_title": title.lower(),
            "normalized_artists": artists.lower(),
        },
    )
    assert r.status_code == 200
    return r.json()["id"], duration_ms


@pytest.mark.asyncio
async def test_manual_youtube_download_success():
    """Test successful manual YouTube download."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, duration_ms = await _create_track(ac, title="Test Track", artists="Test Artist", duration_ms=180000)
        
        # Mock yt-dlp subprocess call
        mock_video_data = {
            'title': 'Test Track (Official Video)',
            'channel': 'Test Artist - Topic',
            'uploader': 'Test Artist',
            'duration': 180
        }
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(mock_video_data)
        
        with patch('subprocess.run', return_value=mock_result):
            # Test with valid YouTube URL
            url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            r = await ac.post(
                f"/api/v1/tracks/{track_id}/youtube/manual_download",
                params={"youtube_url": url}
            )
            
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert "successfully added" in data["message"].lower()
            assert data["video_id"] == "dQw4w9WgXcQ"
            assert data["title"] == "Test Track (Official Video)"
            assert data["channel"] == "Test Artist - Topic"
            assert data["duration_sec"] == 180
            assert "score" in data
            assert "candidate_id" in data
            
            # Verify candidate was created
            candidates_r = await ac.get(f"/api/v1/candidates/enriched?track_id={track_id}")
            assert candidates_r.status_code == 200
            candidates = candidates_r.json()
            assert len(candidates) > 0
            # Find the manually added candidate
            manual_candidate = next((c for c in candidates if c["external_id"] == "dQw4w9WgXcQ"), None)
            assert manual_candidate is not None
            assert manual_candidate["chosen"] is True
            assert manual_candidate["title"] == "Test Track (Official Video)"


@pytest.mark.asyncio
async def test_manual_youtube_download_invalid_url():
    """Test manual download with invalid YouTube URL."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, _ = await _create_track(ac)
        
        # Test with invalid URL
        r = await ac.post(
            f"/api/v1/tracks/{track_id}/youtube/manual_download",
            params={"youtube_url": "https://example.com/not-youtube"}
        )
        
        assert r.status_code == 400
        data = r.json()
        assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_manual_youtube_download_track_not_found():
    """Test manual download with non-existent track."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Use a non-existent track ID
        r = await ac.post(
            f"/api/v1/tracks/99999/youtube/manual_download",
            params={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
        
        assert r.status_code == 404
        data = r.json()
        assert "track not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_manual_youtube_download_various_url_formats():
    """Test manual download with different YouTube URL formats."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, _ = await _create_track(ac)
        
        mock_video_data = {
            'title': 'Test Video',
            'channel': 'Test Channel',
            'duration': 180
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(mock_video_data)
        
        # Test various YouTube URL formats
        test_urls = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]
        
        with patch('subprocess.run', return_value=mock_result):
            for url, expected_video_id in test_urls:
                r = await ac.post(
                    f"/api/v1/tracks/{track_id}/youtube/manual_download",
                    params={"youtube_url": url}
                )
                
                assert r.status_code == 200, f"Failed for URL: {url}"
                data = r.json()
                assert data["video_id"] == expected_video_id, f"Wrong video_id for URL: {url}"


@pytest.mark.asyncio
async def test_manual_youtube_download_metadata_fetch_failure():
    """Test manual download when yt-dlp fails to fetch metadata."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        track_id, _ = await _create_track(ac)
        
        # Mock failed yt-dlp call
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Video unavailable"
        
        with patch('subprocess.run', return_value=mock_result):
            r = await ac.post(
                f"/api/v1/tracks/{track_id}/youtube/manual_download",
                params={"youtube_url": "https://www.youtube.com/watch?v=invalid123"}
            )
            
            assert r.status_code == 400
            data = r.json()
            assert "failed to fetch" in data["detail"].lower()
