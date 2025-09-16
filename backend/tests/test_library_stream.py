import os
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Play Song", artists="Player", duration_ms=90000):
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


async def _enqueue_fake_download(ac: AsyncClient, track_id: int):
    os.environ["DOWNLOAD_FAKE"] = "1"
    # Start worker real mode (simulate_seconds=0) to create the file
    rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
    assert rr.status_code == 200
    r = await ac.post(f"/api/v1/downloads/enqueue?track_id={track_id}")
    assert r.status_code == 200
    # Wait idle and stop
    wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": track_id, "stop_after": True})
    assert wr.status_code == 200


async def test_stream_full_and_range(tmp_path):
    os.environ["LIBRARY_DIR"] = str(tmp_path)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        tid = await _create_track(ac)
        await _enqueue_fake_download(ac, tid)

        # Find library file
        rlib = await ac.get(f"/api/v1/library/files?track_id={tid}")
        assert rlib.status_code == 200
        files = rlib.json()
        assert files
        fid = files[0]["id"]

        # Full content
        rfull = await ac.get(f"/api/v1/library/files/{fid}/stream")
        assert rfull.status_code == 200
        assert rfull.headers.get("accept-ranges") == "bytes"
        assert rfull.headers.get("etag")
        assert rfull.content and len(rfull.content) > 0

        # Partial content
        rpart = await ac.get(f"/api/v1/library/files/{fid}/stream", headers={"Range": "bytes=0-9"})
        assert rpart.status_code == 206
        assert rpart.headers.get("content-range", "").startswith("bytes 0-")
        assert rpart.headers.get("accept-ranges") == "bytes"
        assert rpart.content and len(rpart.content) == 10
