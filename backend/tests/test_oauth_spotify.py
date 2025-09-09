import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_spotify_authorize_and_callback(monkeypatch):
    # Set env secrets
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("SECRET_KEY", "supersecretkey1234567890123456")

    # Mock token endpoint
    async def fake_post(self, url, data=None, **kwargs):  # type: ignore
        class Resp:
            status_code = 200

            def json(self):
                return {
                    "access_token": "AT",
                    "refresh_token": "RT",
                    "expires_in": 3600,
                    "scope": "",
                    "token_type": "Bearer",
                }

            @property
            def text(self):
                return "ok"

        return Resp()

    import httpx as _httpx
    _orig_post = _httpx.AsyncClient.post

    async def selective_post(self, url, data=None, **kwargs):  # type: ignore
        # Only intercept Spotify token endpoint calls
        url_str = str(url)
        if url_str.startswith("https://accounts.spotify.com/"):
            return await fake_post(self, url, data=data, **kwargs)
        # Delegate to original for all other URLs (including the ASGI test client)
        return await _orig_post(self, url, data=data, **kwargs)

    monkeypatch.setattr(_httpx.AsyncClient, "post", selective_post, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # need a spotify account
        r = await ac.post(
            "/api/v1/sources/accounts",
            json={"type": "spotify", "name": "acc", "enabled": True},
        )
        assert r.status_code == 200
        acc_id = r.json()["id"]

        r = await ac.get(f"/api/v1/oauth/spotify/authorize?account_id={acc_id}")
        assert r.status_code == 200
        url = r.json()["authorize_url"]
        assert "state=" in url and "code_challenge=" in url

        # Extract saved state from db by calling callback with same state
        # In a real flow, Spotify would redirect back with code+state
        # Here we fetch the state from the authorize URL for simplicity
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(url).query)
        state = q["state"][0]
        r = await ac.get(f"/api/v1/oauth/spotify/callback?code=fakecode&state={state}")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
