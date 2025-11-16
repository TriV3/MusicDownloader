import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_restart_worker_endpoint():
    """Test that restart_worker endpoint successfully restarts the download worker."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Call restart_worker endpoint
        r = await ac.post("/api/v1/downloads/restart_worker")
        assert r.status_code == 200
        
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "Download worker restarted successfully"


@pytest.mark.asyncio
async def test_restart_worker_when_stuck():
    """Test that restart_worker can recover from a stuck worker."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Start worker in simulate mode
        r = await ac.post("/api/v1/downloads/_restart_worker", json={"concurrency": 1, "simulate_seconds": 0.1})
        assert r.status_code == 200

        # Create a track and enqueue a download
        tr = await ac.post("/api/v1/tracks/", json={"title": "Test Song", "artists": "Test Artist"})
        tid = tr.json()["id"]
        
        # Enqueue download
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200

        # Restart worker (simulates recovery from stuck state)
        r = await ac.post("/api/v1/downloads/restart_worker")
        assert r.status_code == 200
        
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "Download worker restarted successfully"
        
        # Verify we can still enqueue downloads after restart
        r = await ac.post(f"/api/v1/downloads/enqueue?track_id={tid}")
        assert r.status_code == 200
