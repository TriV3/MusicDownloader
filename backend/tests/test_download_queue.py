import asyncio
import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def _create_track(ac: AsyncClient, title="Q Job", artists="Artist", duration_ms=120000):
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


@pytest.mark.asyncio
async def test_enqueue_and_worker_runs_concurrently():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Restart worker from within the app context
        rr = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 2, "simulate_seconds": 0.05})
        assert rr.status_code == 200

        # Create a track
        tid = await _create_track(ac)

        # Enqueue 3 jobs
        for _ in range(3):
            r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
            assert r.status_code == 200

        # Brief delay then list
        await asyncio.sleep(0.05)
        r2 = await ac.get("/api/v1/downloads/?limit=10")
        assert r2.status_code == 200
        items = r2.json()
        assert len(items) >= 3
        # Wait via helper until worker idle and DB terminal states for this track, then stop worker
        wr = await ac.post("/api/v1/downloads/_wait_idle", json={"timeout": 3.0, "track_id": tid, "stop_after": True})
        assert wr.status_code == 200
        # Verify all three completed
        r3 = await ac.get("/api/v1/downloads/?limit=10")
        assert r3.status_code == 200
        items_done = r3.json()
        assert sum(1 for d in items_done if d["status"] == "done") >= 3
