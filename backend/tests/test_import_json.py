import os
import json
import pytest
from httpx import AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


SAMPLE = [
    {"artists": "Artist1", "title": "Title1", "genre": "Pop", "bpm": 120, "duration": "3:00"},
    {"artists": "Artist2", "title": "Title2", "genre": "Rock", "bpm": 90, "duration": "2:30"},
]


@pytest.mark.asyncio
async def test_import_json_dry_run():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # perform dry run
        files = {"file": ("tracks.json", json.dumps(SAMPLE), "application/json")}
        data = {"dry_run": "true"}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data=data)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        assert body["received"] == 2
        assert body["to_create_non_duplicates"] == 2
        assert body["created"] == 0
        assert len(body["errors"]) == 0
        assert body["items"] is not None


@pytest.mark.asyncio
async def test_import_json_create_and_duplicate():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # real import
        files = {"file": ("tracks.json", json.dumps(SAMPLE), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "false"})
        assert r.status_code == 200
        body = r.json()
        assert body["created"] == 2
        # second import -> duplicates skipped
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "false"})
        body2 = r.json()
        assert body2["created"] == 0
        assert body2["to_create_non_duplicates"] == 0


@pytest.mark.asyncio
async def test_import_json_validation_error():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Missing required title should trigger error; empty bpm is acceptable
        bad = [{"artists": "A", "genre": "Pop", "bpm": "", "duration": "3:00"}]
        files = {"file": ("tracks.json", json.dumps(bad), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "true"})
        assert r.status_code == 200
        body = r.json()
        assert body["valid"] == 0
        assert len(body["errors"]) == 1


@pytest.mark.asyncio
async def test_import_json_empty_optional_fields_ok():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        rows = [{"artists": "A", "title": "T", "genre": "", "bpm": "", "duration": ""}]
        files = {"file": ("tracks.json", json.dumps(rows), "application/json")}
        r = await ac.post("/api/v1/tracks/import/json", files=files, data={"dry_run": "true"})
        assert r.status_code == 200
        body = r.json()
        # valid == 1 because empty optional fields are allowed
        assert body["valid"] == 1
        assert len(body["errors"]) == 0