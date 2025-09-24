import os
from pathlib import Path

import pytest
from httpx import AsyncClient

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


@pytest.mark.asyncio
async def test_library_scan_links_files_and_upserts(tmp_path, monkeypatch):
    # Arrange: point LIBRARY_DIR to a temp folder
    lib = tmp_path / "library"
    lib.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LIBRARY_DIR", str(lib))

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create a Track via API
        r = await client.post("/api/v1/tracks/", json={"artists": "Rezone", "title": "Happiness"})
        assert r.status_code == 200
        t = r.json()
        tid = t["id"]
        # Create a dummy audio file with expected naming (including unicode em dash): "Artists — Title.mp3"
        path = lib / "Rezone — Happiness.mp3"
        path.write_bytes(b"\x00" * 1024)  # small placeholder bytes; not a real mp3 but enough for scan

        # Also create an unmatched audio file (should appear in skipped list)
        unmatched = lib / "Unknown Artist - Unknown Song.mp3"
        unmatched.write_bytes(b"\x00" * 256)

        # Act: call scan endpoint
        r2 = await client.post("/api/v1/library/files/scan")
        assert r2.status_code == 200
        data = r2.json()
        assert data["scanned"] >= 1
        assert data["matched"] >= 1
        # Skipped list should include the unmatched file
        assert "skipped_files" in data
        assert any(Path(s).name == unmatched.name for s in data["skipped_files"])

        # Assert: LibraryFile exists and is linked to our track
        r3 = await client.get(f"/api/v1/library/files?track_id={tid}")
        assert r3.status_code == 200
        files = r3.json()
        assert isinstance(files, list)
        assert len(files) == 1
        lf = files[0]
        assert lf["track_id"] == tid
        assert Path(lf["filepath"]).name == path.name
