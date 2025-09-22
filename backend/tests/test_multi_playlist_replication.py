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


async def _create_track(ac: AsyncClient, title="Replicated Song", artists="Multi Artist", duration_ms=150000):
    r = await ac.post("/api/v1/tracks/", json={
        "title": title,
        "artists": artists,
        "duration_ms": duration_ms,
    })
    assert r.status_code == 200
    return r.json()["id"], title, artists


async def _create_spotify_playlist(ac: AsyncClient, name: str):
    r = await ac.post("/api/v1/playlists/", json={
        "provider": "spotify",
        "name": name,
    })
    assert r.status_code == 200
    return r.json()["id"], name


async def _link(ac: AsyncClient, playlist_id: int, track_id: int):
    r = await ac.post("/api/v1/playlist_tracks/", json={
        "playlist_id": playlist_id,
        "track_id": track_id,
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_download_replicates_across_playlists(tmp_path: Path):
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path / "library")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid, title, artists = await _create_track(ac)
        pid1, name1 = await _create_spotify_playlist(ac, "Chill Vibes")
        pid2, name2 = await _create_spotify_playlist(ac, "Focus Mix")
        await _link(ac, pid1, tid)
        await _link(ac, pid2, tid)

        # Start worker real mode
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        # Both playlist copies must exist
        base = Path(os.environ["LIBRARY_DIR"]) / "spotify"
        f1 = base / name1 / f"{artists} - {title}.mp3"
        f2 = base / name2 / f"{artists} - {title}.mp3"
        assert f1.exists(), f"Missing replicated copy in {f1}"
        assert f2.exists(), f"Missing replicated copy in {f2}"
