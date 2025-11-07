import os
import pytest
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DOWNLOAD_FAKE", "1")

try:
    from backend.app.db.session import async_session
    from backend.app.db.models.models import (
        Track,
        Download,
        DownloadStatus,
        SearchCandidate,
        SearchProvider,
        Playlist,
        PlaylistTrack,
        SourceAccount,
    )
    from backend.app.worker.downloads_worker import DownloadQueue
except Exception:  # pragma: no cover
    from app.db.session import async_session
    from app.db.models.models import (
        Track,
        Download,
        DownloadStatus,
        SearchCandidate,
        SearchProvider,
        Playlist,
        PlaylistTrack,
        SourceAccount,
    )
    from app.worker.downloads_worker import DownloadQueue


@pytest.mark.asyncio
async def test_spotify_cover_preserved_after_download(tmp_path, monkeypatch):
    """Test that Spotify cover URL in database is NOT overwritten by YouTube thumbnail after download.
    
    Scenario:
    1. Track has a Spotify cover URL (https://i.scdn.co/...)
    2. Download is performed using a YouTube candidate
    3. After download completes, track cover_url should still be the Spotify URL
    """
    # Set up test library directory
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    monkeypatch.setenv("LIBRARY_DIR", str(lib_dir))
    monkeypatch.setenv("DOWNLOAD_FAKE", "1")
    
    # Use unique identifiers to avoid UNIQUE constraint violations
    unique_id = str(uuid.uuid4())[:8]
    spotify_cover_url = "https://i.scdn.co/image/ab67616d0000b273test123"
    
    async with async_session() as session:
        # Create source account
        source_account = SourceAccount(
            type="spotify",
            name=f"Test User {unique_id}",
            enabled=True
        )
        session.add(source_account)
        await session.flush()
        
        # Create playlist
        playlist = Playlist(
            name=f"Test Playlist {unique_id}",
            provider="spotify",
            source_account_id=source_account.id,
            provider_playlist_id=f"test_playlist_{unique_id}"
        )
        session.add(playlist)
        await session.flush()
        
        # Create track with Spotify cover
        track = Track(
            title="Test Song",
            artists="Test Artist",
            album="Test Album",
            normalized_title="test song",
            normalized_artists="test artist",
            duration_ms=180000,
            cover_url=spotify_cover_url,  # Spotify cover already set
        )
        session.add(track)
        await session.flush()
        
        # Add track to playlist
        pt = PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            position=1,
        )
        session.add(pt)
        await session.flush()
        
        # Create YouTube candidate
        candidate = SearchCandidate(
            track_id=track.id,
            provider=SearchProvider.youtube,
            external_id="test_video_123",
            url="https://www.youtube.com/watch?v=test123",
            title="Test Song - Official Audio",
            score=0.95,
            duration_sec=180,
            chosen=True
        )
        session.add(candidate)
        await session.flush()
        
        # Create download
        download = Download(
            track_id=track.id,
            candidate_id=candidate.id,
            provider="yt_dlp",
            status=DownloadStatus.queued
        )
        session.add(download)
        await session.commit()
        download_id = download.id
        track_id = track.id
    
    # Process download through worker
    queue = DownloadQueue()
    from backend.app.worker.downloads_worker import DownloadJob
    job = DownloadJob(download_id=download_id)
    await queue._process_job(job)
    
    # Verify that Spotify cover was preserved
    async with async_session() as session:
        track = await session.get(Track, track_id)
        assert track is not None
        assert track.cover_url == spotify_cover_url, (
            f"Spotify cover was overwritten! Expected {spotify_cover_url}, "
            f"got {track.cover_url}"
        )
        print(f"✓ Spotify cover preserved after download: {track.cover_url}")


@pytest.mark.asyncio
async def test_youtube_cover_set_when_no_cover_exists(tmp_path, monkeypatch):
    """Test that YouTube thumbnail IS set when track has no cover URL."""
    # Set up test library directory
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    monkeypatch.setenv("LIBRARY_DIR", str(lib_dir))
    monkeypatch.setenv("DOWNLOAD_FAKE", "1")
    
    # Use unique identifiers to avoid UNIQUE constraint violations
    unique_id = str(uuid.uuid4())[:8]
    
    async with async_session() as session:
        # Create source account
        source_account = SourceAccount(
            type="spotify",
            name=f"Test User {unique_id}",
            enabled=True
        )
        session.add(source_account)
        await session.flush()
        
        # Create playlist
        playlist = Playlist(
            name=f"Test Playlist {unique_id}",
            provider="spotify",
            source_account_id=source_account.id,
            provider_playlist_id=f"test_playlist_{unique_id}"
        )
        session.add(playlist)
        await session.flush()
        
        # Create track WITHOUT cover
        track = Track(
            title="Test Song 2",
            artists="Test Artist 2",
            album="Test Album 2",
            normalized_title="test song 2",
            normalized_artists="test artist 2",
            duration_ms=200000,
            cover_url=None,  # No cover
        )
        session.add(track)
        await session.flush()
        
        # Add track to playlist
        pt = PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            position=1,
        )
        session.add(pt)
        await session.flush()
        
        # Create YouTube candidate
        candidate = SearchCandidate(
            track_id=track.id,
            provider=SearchProvider.youtube,
            external_id="test_video_456",
            url="https://www.youtube.com/watch?v=test456",
            title="Test Song 2 - Official Audio",
            score=0.90,
            duration_sec=200,
            chosen=True
        )
        session.add(candidate)
        await session.flush()
        
        # Create download
        download = Download(
            track_id=track.id,
            candidate_id=candidate.id,
            provider="yt_dlp",
            status=DownloadStatus.queued
        )
        session.add(download)
        await session.commit()
        download_id = download.id
        track_id = track.id
    
    # Process download through worker
    queue = DownloadQueue()
    from backend.app.worker.downloads_worker import DownloadJob
    job = DownloadJob(download_id=download_id)
    await queue._process_job(job)
    
    # Verify that YouTube cover was set
    async with async_session() as session:
        track = await session.get(Track, track_id)
        assert track is not None
        assert track.cover_url is not None, "YouTube cover should have been set"
        assert "img.youtube.com" in track.cover_url or "i.ytimg.com" in track.cover_url, (
            f"Expected YouTube thumbnail URL, got {track.cover_url}"
        )
        print(f"✓ YouTube cover set when no cover existed: {track.cover_url}")


@pytest.mark.asyncio
async def test_youtube_cover_can_replace_youtube_cover(tmp_path, monkeypatch):
    """Test that YouTube thumbnail can be updated if current cover is also YouTube."""
    # Set up test library directory
    lib_dir = tmp_path / "library"
    lib_dir.mkdir()
    monkeypatch.setenv("LIBRARY_DIR", str(lib_dir))
    monkeypatch.setenv("DOWNLOAD_FAKE", "1")
    
    # Use unique identifiers to avoid UNIQUE constraint violations
    unique_id = str(uuid.uuid4())[:8]
    old_youtube_cover = "https://img.youtube.com/vi/old_video/hqdefault.jpg"
    
    async with async_session() as session:
        # Create source account
        source_account = SourceAccount(
            type="spotify",
            name=f"Test User {unique_id}",
            enabled=True
        )
        session.add(source_account)
        await session.flush()
        
        # Create playlist
        playlist = Playlist(
            name=f"Test Playlist {unique_id}",
            provider="spotify",
            source_account_id=source_account.id,
            provider_playlist_id=f"test_playlist_{unique_id}"
        )
        session.add(playlist)
        await session.flush()
        
        # Create track with old YouTube cover
        track = Track(
            title="Test Song 3",
            artists="Test Artist 3",
            album="Test Album 3",
            normalized_title="test song 3",
            normalized_artists="test artist 3",
            duration_ms=190000,
            cover_url=old_youtube_cover,  # Old YouTube cover
        )
        session.add(track)
        await session.flush()
        
        # Add track to playlist
        pt = PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            position=1,
        )
        session.add(pt)
        await session.flush()
        
        # Create YouTube candidate with different ID
        candidate = SearchCandidate(
            track_id=track.id,
            provider=SearchProvider.youtube,
            external_id="new_video_789",
            url="https://www.youtube.com/watch?v=new_video_789",
            title="Test Song 3 - Official Audio",
            score=0.92,
            duration_sec=190,
            chosen=True
        )
        session.add(candidate)
        await session.flush()
        
        # Create download
        download = Download(
            track_id=track.id,
            candidate_id=candidate.id,
            provider="yt_dlp",
            status=DownloadStatus.queued
        )
        session.add(download)
        await session.commit()
        download_id = download.id
        track_id = track.id
    
    # Process download through worker
    queue = DownloadQueue()
    from backend.app.worker.downloads_worker import DownloadJob
    job = DownloadJob(download_id=download_id)
    await queue._process_job(job)
    
    # Verify that YouTube cover was updated
    async with async_session() as session:
        track = await session.get(Track, track_id)
        assert track is not None
        assert track.cover_url != old_youtube_cover, (
            "YouTube cover should have been updated"
        )
        assert "new_video_789" in track.cover_url, (
            f"Expected new YouTube thumbnail, got {track.cover_url}"
        )
        print(f"✓ YouTube cover updated from old YouTube cover: {track.cover_url}")
