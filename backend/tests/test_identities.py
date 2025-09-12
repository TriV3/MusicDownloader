import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_identity_auto_created_with_track():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/tracks/",
            json={
                "title": "Song A",
                "artists": "Artist A",
                "normalized_title": "song a",
                "normalized_artists": "artist a",
            },
        )
        assert r.status_code == 200
        track_id = r.json()["id"]
        # list identities for track
        r2 = await ac.get("/api/v1/identities/", params={"track_id": track_id})
        assert r2.status_code == 200
        data = r2.json()
        assert len(data) == 1
        ident = data[0]
        assert ident["provider"] == "manual"
        assert ident["provider_track_id"].startswith("manual:")


@pytest.mark.asyncio
async def test_identity_crud_and_filters():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Need a track
        track_resp = await ac.post(
            "/api/v1/tracks/",
            json={
                "title": "Song B",
                "artists": "Artist B",
                "normalized_title": "song b",
                "normalized_artists": "artist b",
            },
        )
        track_id = track_resp.json()["id"]

        # Create another identity manually
        r = await ac.post(
            "/api/v1/identities/",
            json={
                "track_id": track_id,
                "provider": "spotify",
                "provider_track_id": "sp123",
                "provider_url": "https://open.spotify.com/track/sp123",
                "fingerprint": None,
            },
        )
        assert r.status_code == 200
        ident_id = r.json()["id"]

        # List with fingerprint filter false
        r2 = await ac.get("/api/v1/identities/", params={"has_fingerprint": False})
        assert r2.status_code == 200
        assert any(i["id"] == ident_id for i in r2.json())

        # Update identity add fingerprint
        r3 = await ac.put(
            f"/api/v1/identities/{ident_id}",
            json={
                "track_id": track_id,
                "provider": "spotify",
                "provider_track_id": "sp123",
                "provider_url": "https://open.spotify.com/track/sp123",
                "fingerprint": "abc123",
            },
        )
        assert r3.status_code == 200
        assert r3.json()["fingerprint"] == "abc123"

        # Now filter with has_fingerprint true
        r4 = await ac.get("/api/v1/identities/", params={"has_fingerprint": True})
        assert r4.status_code == 200
        assert any(i["fingerprint"] == "abc123" for i in r4.json())

        # Delete
        r5 = await ac.delete(f"/api/v1/identities/{ident_id}")
        assert r5.status_code == 200
        assert r5.json()["deleted"] is True