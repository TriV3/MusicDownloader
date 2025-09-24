import pytest
from pathlib import Path
from httpx import AsyncClient

try:
    from backend.app.main import app
except Exception:  # pragma: no cover
    from app.main import app


@pytest.mark.asyncio
async def test_reverse_reindex_links_files_from_tracks(tmp_path, monkeypatch):
    # Arrange
    lib = tmp_path / "library"
    lib.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LIBRARY_DIR", str(lib))

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create two tracks
        r1 = await client.post("/api/v1/tracks/", json={"artists": "Rezone", "title": "Happiness"})
        assert r1.status_code == 200
        t1 = r1.json()
        tid1 = t1["id"]

        r2 = await client.post("/api/v1/tracks/", json={"artists": "Unknown Artist", "title": "Missing Song"})
        assert r2.status_code == 200
        t2 = r2.json()
        tid2 = t2["id"]

        # Create only the first file on disk (use em dash to validate normalization)
        p1 = lib / "Rezone — Happiness.mp3"
        p1.write_bytes(b"\x00" * 1024)

        # Act: reverse reindex
        r3 = await client.post("/api/v1/library/files/reindex_from_tracks")
        assert r3.status_code == 200
        data = r3.json()
        assert data["tracks_checked"] >= 2
        assert data["tracks_found"] >= 1
        assert data["linked_added"] >= 1

        # Verify library file linked to first track
        r4 = await client.get(f"/api/v1/library/files?track_id={tid1}")
        assert r4.status_code == 200
        files = r4.json()
        assert len(files) == 1
        assert Path(files[0]["filepath"]).name == p1.name

        # Verify missing tracks include the second track
        ids = {s["id"] for s in data.get("missing_samples", [])}
        assert tid2 in ids or data.get("tracks_missing", 0) >= 1
