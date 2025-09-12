import os
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_preview_normalization_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/v1/tracks/normalize/preview", params={"artists": "Artist ft. Guest", "title": "Song (Live) - Radio Edit"})
        assert r.status_code == 200
        data = r.json()
        assert data["primary_artist"] == "Artist"
        assert data["normalized_title"] == "song"
        assert data["is_live"] is True
        assert data["is_remix_or_edit"] is True
