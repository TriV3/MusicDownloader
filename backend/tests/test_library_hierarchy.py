import os
from pathlib import Path

import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Happiness", artists="Rezone", duration_ms=180000):
    r = await ac.post("/api/v1/tracks/", json={
        "title": title,
        "artists": artists,
        "duration_ms": duration_ms,
        "genre": "House",
        "bpm": 124,
    })
    assert r.status_code == 200
    return r.json()["id"]


async def _create_spotify_playlist(ac: AsyncClient, name="Twilight Beats"):
    r = await ac.post("/api/v1/playlists/", json={
        "provider": "spotify",
        "name": name,
    })
    assert r.status_code == 200
    return r.json()["id"], name


async def _link_track_to_playlist(ac: AsyncClient, playlist_id: int, track_id: int):
    r = await ac.post("/api/v1/playlist_tracks/", json={
        "playlist_id": playlist_id,
        "track_id": track_id,
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_download_hierarchy_spotify_playlist(tmp_path: Path):
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path / "library")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create spotify playlist and track, link them
        pid, pname = await _create_spotify_playlist(ac)
        tid = await _create_track(ac, title="Happiness", artists="Rezone")
        await _link_track_to_playlist(ac, pid, tid)

        # Start worker (real mode) and enqueue
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200

        # Wait idle and stop
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        # Verify library file under provider/playlist
        lib = Path(os.environ["LIBRARY_DIR"]) / "spotify" / pname / "Rezone - Happiness.mp3"
        assert lib.exists(), f"Expected file at {lib}"


@pytest.mark.asyncio
async def test_download_hierarchy_other_no_playlist(tmp_path: Path):
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path / "library")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid = await _create_track(ac, title="Track", artists="Artist")

        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200

        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        lib = Path(os.environ["LIBRARY_DIR"]) / "other" / "Artist - Track.mp3"
        assert lib.exists(), f"Expected file at {lib}"