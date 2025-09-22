import os
import asyncio
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Dup Test", artists="Artist", duration_ms=120000):
    r = await ac.post("/api/v1/tracks/", json={
        "title": title,
        "artists": artists,
        "duration_ms": duration_ms,
        "genre": "Pop",
        "bpm": 120,
    })
    assert r.status_code == 200
    return r.json()["id"]


async def test_prevent_duplicate_enqueue(tmp_path):
    # Use fake downloader and a temp library dir
    os.environ["DOWNLOAD_FAKE"] = "1"
    os.environ["LIBRARY_DIR"] = str(tmp_path)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start real worker (simulate_seconds=0) to produce a file
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0})
        assert rr.status_code == 200

        tid = await _create_track(ac)

        # First enqueue should perform a fake download and create a LibraryFile
        r1 = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r1.status_code == 200
        dl1 = r1.json()
        assert dl1["status"] in ("queued", "running", "done")

        # Wait for completion and stop worker
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200

        # Verify there is at least one library file
        lr = await ac.get(f"/api/v1/library/files?track_id={tid}")
        assert lr.status_code == 200
        lib_items = lr.json()
        assert len(lib_items) >= 1

        # Enqueue again: should return status=already and not queue work
        r2 = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r2.status_code == 200
        dl2 = r2.json()
        assert dl2["status"] == "already"
        assert dl2.get("filepath")

        # Ensure that calling wait_idle (with no running worker) returns quickly
        wr2 = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 0.5})
        assert wr2.status_code == 200
