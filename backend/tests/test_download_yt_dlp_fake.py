import os
import asyncio
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="DL Song", artists="DL Artist", duration_ms=120000):
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
    return r.json()["id"]


async def _create_youtube_candidate(ac: AsyncClient, track_id: int):
    r = await ac.post(
        "/api/v1/candidates/",
        json={
            "track_id": track_id,
            "provider": "youtube",
            "external_id": "fake-video",
            "url": "https://youtu.be/fake-video",
            "title": "DL Song (Official)",
            "score": 0.99,
            "duration_sec": 120,
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


async def _list_downloads(ac: AsyncClient):
    r = await ac.get("/api/v1/downloads/?limit=5")
    assert r.status_code == 200
    return r.json()


async def test_fake_download_creates_file(tmp_path):
    # Force fake mode so we don't require yt-dlp/ffmpeg in CI
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start real worker (no simulate) so it executes downloader
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200

        tid = await _create_track(ac)
        cid = await _create_youtube_candidate(ac, tid)

        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}&candidate_id={cid}")
        assert r.status_code == 200

        # Wait for completion
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        items = await _list_downloads(ac)
        assert len(items) >= 1
        last = items[0]
        assert last["status"] == "done"
        # Verify a file exists in tmp_path
    import pathlib
    # Hierarchical layout: search recursively
    files = list(pathlib.Path(tmp_path).rglob("*.*"))
    assert files, "No output file generated in fake mode"