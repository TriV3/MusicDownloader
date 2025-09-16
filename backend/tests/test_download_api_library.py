import os
import asyncio
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Lib Song", artists="Lib Artist", duration_ms=120000):
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
            "external_id": "fake-video-lib",
            "url": "https://youtu.be/fake-video-lib",
            "title": "Lib Song (Official)",
            "score": 0.99,
            "duration_sec": 120,
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


async def test_library_file_created_and_listed(tmp_path):
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start real worker
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200

        tid = await _create_track(ac)
        cid = await _create_youtube_candidate(ac, tid)

        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}&candidate_id={cid}")
        assert r.status_code == 200
        dl_id = r.json()["id"]

        # Wait until done and stop worker
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        # Check library files list
        rlib = await ac.get(f"/api/v1/library/files?track_id={tid}")
        assert rlib.status_code == 200
        files = rlib.json()
        assert files, "Library files list is empty"
        assert any(f["track_id"] == tid for f in files)

        # Test downloading the first library file
        fid = files[0]["id"]
        rdl = await ac.get(f"/api/v1/library/files/{fid}/download")
        assert rdl.status_code == 200
        # Starlette FileResponse streams bytes; in tests via httpx it is fully available
        assert rdl.content is not None
        assert len(rdl.content) > 0

        # Track should now have a cover_url set from YouTube thumbnail
        rt = await ac.get(f"/api/v1/tracks/{tid}")
        assert rt.status_code == 200
        cover = rt.json().get("cover_url")
        assert isinstance(cover, str) and cover.startswith("https://img.youtube.com/vi/")


async def test_cancel_download_queued():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start worker with long simulate to keep job queued/running
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0.2})
        assert rr.status_code == 200

        tid = await _create_track(ac, title="Cancel Song")
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200
        dl = r.json()

        # Immediately cancel (likely still queued)
        rc = await ac.post(f"/api/v1/downloads/cancel/{dl['id']}")
        assert rc.status_code in (200, 409)  # If already running, 409 is acceptable

        # Wait idle and stop
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        # Verify final status is not running
        rfinal = await ac.get(f"/api/v1/downloads/{dl['id']}")
        assert rfinal.status_code == 200
        assert rfinal.json()["status"] in ("skipped", "done", "failed")
