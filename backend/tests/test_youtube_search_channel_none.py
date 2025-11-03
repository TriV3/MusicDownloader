import os
import asyncio
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")

try:
    from backend.app.main import app  # type: ignore
except Exception:  # pragma: no cover
    from app.main import app  # type: ignore


async def test_youtube_search_handles_malformed_channel(monkeypatch):
    # Force provider to yts_python
    monkeypatch.setenv("YOUTUBE_SEARCH_PROVIDER", "yts_python")
    # Ensure fake mode disabled for this test only (avoid interfering with other tests relying on fake=1)
    monkeypatch.setenv("YOUTUBE_SEARCH_FAKE", "0")

    # Patch VideosSearch to return an item with channel dict lacking name/id
    from backend.app.utils import youtube_search as ys

    class DummyVS:
        def __init__(self, *a, **kw):
            pass
        def result(self):
            return {"result": [
                {"id": "abc123", "title": "Ausmax - Feel Good", "link": "https://youtu.be/abc123", "channel": {"name": None, "id": None}, "duration": "3:15"},
                {"id": "def456", "title": "Ausmax - Feel Good (Official)", "link": "https://youtu.be/def456", "channel": {"name": "Channel OK", "id": "chan2"}, "duration": "4:05"},
            ]}
        def next(self):
            return {"result": []}

    monkeypatch.setattr(ys, "VideosSearch", DummyVS)

    # Create a track first
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/api/v1/tracks/", json={
            "title": "Feel Good",
            "artists": "Ausmax",
            "duration_ms": 195000,
            "normalized_title": "feel good",
            "normalized_artists": "ausmax"
        })
        assert r.status_code == 200
        tid = r.json()["id"]

        r2 = await ac.get(f"/api/v1/tracks/{tid}/youtube/search?prefer_extended=true&persist=false")
        assert r2.status_code == 200
        data = r2.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Ensure no 500 and at least the valid second item passed through
        assert any("Channel OK" in (item.get("channel") or "") for item in data if isinstance(item, dict))
