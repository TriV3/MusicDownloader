import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


@pytest.mark.asyncio
async def test_track_creation_auto_normalizes_and_creates_identity():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        payload = {
            "title": "Beyoncé - Halo (Live)",
            "artists": "Beyoncé",
        }
        r = await ac.post("/api/v1/tracks/", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["normalized_title"] == "beyonce halo live" or data["normalized_title"].startswith("beyonce")
        assert data["normalized_artists"] == "beyonce"
        # fetch identities list and ensure manual identity exists
        r2 = await ac.get("/api/v1/identities/", params={"track_id": data["id"]})
        assert r2.status_code == 200
        identities = r2.json()
        assert len(identities) == 1
        assert identities[0]["provider"] == "manual"
