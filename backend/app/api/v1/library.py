from __future__ import annotations

from datetime import datetime
import re
from typing import List, Optional
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import platform
import subprocess
import os
from email.utils import formatdate
from datetime import datetime
from typing import AsyncIterator, Optional
from typing import Tuple, Dict, List

try:
    from ...utils.http_range import parse_http_range, build_content_range_header, pick_audio_mime_from_path  # type: ignore
    from ...core.config import settings  # type: ignore
    from ...utils.normalize import normalize_track  # type: ignore
    from ...db.models.models import Track  # type: ignore
except Exception:  # pragma: no cover
    from utils.http_range import parse_http_range, build_content_range_header, pick_audio_mime_from_path  # type: ignore
    from core.config import settings  # type: ignore
    from utils.normalize import normalize_track  # type: ignore
    from db.models.models import Track  # type: ignore

try:  # package mode
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import LibraryFile  # type: ignore
    from ...schemas.models import LibraryFileRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import LibraryFile  # type: ignore
    from schemas.models import LibraryFileRead  # type: ignore


router = APIRouter(prefix="/library/files", tags=["library"])


@router.get("/", response_model=List[LibraryFileRead])
async def list_library_files(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    limit: int = Query(500, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    stmt = select(LibraryFile).where(LibraryFile.exists == True)  # noqa: E712
    if track_id is not None:
        stmt = stmt.where(LibraryFile.track_id == track_id)
    stmt = stmt.order_by(desc(LibraryFile.id)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.scalars().all()


# Accept both with and without trailing slash
@router.get("", response_model=List[LibraryFileRead])
async def list_library_files_no_slash(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    limit: int = Query(500, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    stmt = select(LibraryFile).where(LibraryFile.exists == True)  # noqa: E712
    if track_id is not None:
        stmt = stmt.where(LibraryFile.track_id == track_id)
    stmt = stmt.order_by(desc(LibraryFile.id)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{file_id}", response_model=LibraryFileRead)
async def get_library_file(file_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(LibraryFile, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="LibraryFile not found")
    return item


@router.delete("/{file_id}")
async def delete_library_file(file_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(LibraryFile, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="LibraryFile not found")
    # Best-effort: remove file on disk if exists
    try:
        if item.filepath:
            p = Path(item.filepath)
            if p.exists():
                p.unlink()
    except Exception:
        # Ignore file deletion errors
        pass
    await session.delete(item)
    return {"deleted": True}


@router.get("/{file_id}/download")
async def download_library_file(file_id: int, session: AsyncSession = Depends(get_session)):
    """Stream the library file over HTTP for browser download."""
    item = await session.get(LibraryFile, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="LibraryFile not found")
    if not item.filepath:
        raise HTTPException(status_code=404, detail="File path is missing")
    path = Path(item.filepath)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    # Let Starlette infer content-type; use attachment disposition for download
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.post("/{file_id}/reveal")
async def reveal_in_explorer(file_id: int, session: AsyncSession = Depends(get_session)):
    """On Windows, open Explorer and select the file. No-op on unsupported OS."""
    if platform.system() != "Windows":
        raise HTTPException(status_code=501, detail="Reveal is only supported on Windows")

    item = await session.get(LibraryFile, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="LibraryFile not found")
    if not item.filepath:
        raise HTTPException(status_code=404, detail="File path is missing")
    # Normalize to an absolute Windows path
    path = Path(item.filepath).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # explorer /select,"C:\path\to\file"
    try:
            # Preferred: pass '/select,' and the path as separate args (handles spaces properly)
            r = subprocess.run(["explorer", "/select,", str(path)], check=False)
        # If Explorer didn't open the correct location for any reason, fallback to opening the folder
        # Note: We cannot easily detect correctness here; provide a best-effort fallback when returncode is non-zero
            if r.returncode not in (None, 0):  # pragma: no cover
                # Try via cmd 'start' which is sometimes more reliable with selection
                r2 = subprocess.run(["cmd", "/c", "start", "", "/select,", str(path)], check=False)
                if r2.returncode not in (None, 0):
                    subprocess.run(["explorer", str(path.parent)], check=False)
    except Exception as ex:  # pragma: no cover - hard to simulate in tests
        raise HTTPException(status_code=500, detail=f"Failed to open Explorer: {ex}")
    return {"ok": True, "path": str(path)}


@router.get("/{file_id}/stream")
async def stream_library_file(file_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    """Stream a library file with HTTP Range support for in-browser playback/seek.

    - Supports a single byte range (sufficient for <audio> seek behavior)
    - Returns 200 for full content, 206 for partial
    - Provides ETag/Last-Modified/Cache-Control and Accept-Ranges headers
    """
    item = await session.get(LibraryFile, file_id)
    if not item:
        raise HTTPException(status_code=404, detail="LibraryFile not found")
    if not item.filepath:
        raise HTTPException(status_code=404, detail="File path is missing")
    path = Path(item.filepath)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    stat = path.stat()
    file_size = stat.st_size
    last_modified = formatdate(stat.st_mtime, usegmt=True)

    # Prefer DB checksum for strong-ish ETag; otherwise use size+mtime as weak validator
    checksum = item.checksum_sha256
    etag = f'W/"sha256-{checksum}"' if checksum else f'W/"{stat.st_mtime_ns}-{file_size}"'

    # Handle If-None-Match for simple client cache validation
    inm = request.headers.get("if-none-match")
    if inm and inm.strip() == etag:
        return Response(status_code=304, headers={
            "ETag": etag,
            "Last-Modified": last_modified,
            "Cache-Control": "public, max-age=3600",
        })

    # Determine content-type
    media_type = pick_audio_mime_from_path(str(path))

    # Parse Range header
    range_header = request.headers.get("range")
    try:
        byte_range = parse_http_range(range_header, file_size)
    except ValueError:
        return Response(status_code=416, headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes */{file_size}",
            "ETag": etag,
            "Last-Modified": last_modified,
            "Cache-Control": "public, max-age=3600",
        })

    if byte_range is None:
        status_code = 200
        start, end = 0, file_size - 1
    else:
        status_code = 206
        start, end = byte_range

    content_length = end - start + 1

    def file_iter(p: Path, start_byte: int, end_byte: int, chunk_size: int = 64 * 1024):
        with p.open("rb") as f:
            f.seek(start_byte)
            remaining = end_byte - start_byte + 1
            while remaining > 0:
                to_read = min(chunk_size, remaining)
                chunk = f.read(to_read)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": "public, max-age=3600",
        "Content-Length": str(content_length),
    }
    if status_code == 206:
        headers["Content-Range"] = build_content_range_header(start, end, file_size)

    return StreamingResponse(file_iter(path, start, end), status_code=status_code, media_type=media_type, headers=headers)


@router.post("/resync", tags=["library"], summary="Rebuild LibraryFile entries from completed downloads", include_in_schema=False)
async def resync_library_files(session: AsyncSession = Depends(get_session)):
    """Best-effort maintenance endpoint that scans completed downloads and ensures LibraryFile rows exist.

    Useful if the UI shows no library files due to earlier worker failures; it will upsert entries
    for any download with a filepath that exists on disk.
    """
    try:
        from ...db.models.models import Download, DownloadStatus, LibraryFile  # type: ignore
        from sqlalchemy import select as _select
    except Exception:  # pragma: no cover
        from db.models.models import Download, DownloadStatus, LibraryFile  # type: ignore
        from sqlalchemy import select as _select

    result = await session.execute(
        _select(Download).where(Download.status == DownloadStatus.done)
    )
    rows = result.scalars().all()
    added = 0
    updated = 0
    for dl in rows:
        if not dl.filepath:
            continue
        p = Path(dl.filepath)
        if not p.exists():
            continue
        try:
            st = p.stat()
            mtime = datetime.utcfromtimestamp(st.st_mtime)
            size = int(st.st_size)
        except Exception:
            mtime = datetime.utcnow()
            size = getattr(dl, "filesize_bytes", 0) or 0

        res2 = await session.execute(_select(LibraryFile).where(LibraryFile.filepath == str(p)))
        lf = res2.scalars().first()
        if lf:
            lf.track_id = dl.track_id
            lf.file_mtime = mtime
            lf.file_size = size
            lf.checksum_sha256 = dl.checksum_sha256
            lf.exists = True
            updated += 1
        else:
            lf = LibraryFile(
                track_id=dl.track_id,
                filepath=str(p),
                file_mtime=mtime,
                file_size=size,
                checksum_sha256=dl.checksum_sha256,
                exists=True,
            )
            session.add(lf)
            added += 1
    await session.flush()
    return {"ok": True, "added": added, "updated": updated}


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp3", ".m4a", ".aac", ".flac", ".wav", ".opus", ".webm"}


async def _infer_track_id_from_filename(session: AsyncSession, filename: str) -> Optional[int]:
    name = Path(filename).stem
    # Accept unicode dash variants between artists and title
    # Normalize to a simple hyphen splitter
    name_norm = name.replace("–", "-").replace("—", "-")
    # Expect pattern: "Artists - Title"
    if " - " not in name_norm and "-" in name_norm:
        # Ensure there's spacing for robustness
        name_norm = re.sub(r"\s*-\s*", " - ", name_norm)
    if " - " not in name_norm:
        return None
    artists, title = name_norm.split(" - ", 1)
    artists = artists.strip()
    title = title.strip()
    if not artists or not title:
        return None
    norm = normalize_track(artists, title)
    from sqlalchemy import select as _select, desc as _desc
    res = await session.execute(
        _select(Track)
        .where(Track.normalized_artists == norm.normalized_artists, Track.normalized_title == norm.normalized_title)
        .order_by(_desc(Track.updated_at))
    )
    t = res.scalars().first()
    return t.id if t else None


def _normalized_key_from_filename(filename: str) -> Optional[Tuple[str, str]]:
    """Parse a filename of the form 'Artists - Title.ext' (accepting unicode dashes)
    and return (normalized_artists, normalized_title).
    """
    name = Path(filename).stem
    name_norm = name.replace("–", "-").replace("—", "-")
    if " - " not in name_norm and "-" in name_norm:
        name_norm = re.sub(r"\s*-\s*", " - ", name_norm)
    if " - " not in name_norm:
        return None
    artists, title = name_norm.split(" - ", 1)
    artists = artists.strip()
    title = title.strip()
    if not artists or not title:
        return None
    norm = normalize_track(artists, title)
    return (norm.normalized_artists, norm.normalized_title)


@router.post("/scan", tags=["library"], summary="Scan library directory and upsert LibraryFile entries")
async def scan_library(
    session: AsyncSession = Depends(get_session),
    compute_checksum: bool = Query(False, description="Compute checksum_sha256 (slower)"),
    max_files: int = Query(2000, ge=1, le=10000),
    analyze_metadata: bool = Query(
        True,
        description="When true, attempt to analyze audio metadata (duration) using ffprobe if Track.duration_ms is missing."
    ),
):
    """Walk the configured library directory and upsert LibraryFile rows for files that match an existing Track.

    Matching strategy: infer (artists, title) from filename pattern "Artists - Title.ext" and match by normalized fields.
    Only files with known audio extensions are considered. Files that do not match an existing Track are skipped.
    """
    try:
        from ...db.models.models import LibraryFile  # type: ignore
        from sqlalchemy import select as _select
    except Exception:  # pragma: no cover
        from db.models.models import LibraryFile  # type: ignore
        from sqlalchemy import select as _select

    # Determine library dir
    lib_dir = Path(os.environ.get("LIBRARY_DIR") or settings.library_dir).resolve()
    if not lib_dir.exists() or not lib_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Library directory not found: {lib_dir}")

    scanned = 0
    matched = 0
    added = 0
    updated = 0
    skipped = 0
    skipped_files: list[str] = []

    # Walk directory
    for root, _, files in os.walk(lib_dir):
        for fn in files:
            if scanned >= max_files:
                break
            p = Path(root) / fn
            if not _is_audio_file(p):
                continue
            scanned += 1
            track_id = await _infer_track_id_from_filename(session, p.name)
            if not track_id:
                skipped += 1
                try:
                    # Provide a relative path for readability in UI
                    rel = str(p.resolve().relative_to(lib_dir))
                except Exception:
                    rel = str(p)
                skipped_files.append(rel)
                continue
            matched += 1
            try:
                st = p.stat()
                mtime = datetime.utcfromtimestamp(st.st_mtime)
                size = int(st.st_size)
            except Exception:
                mtime = datetime.utcnow()
                size = 0

            checksum = None
            if compute_checksum:
                # Lazy import to avoid overhead if not requested
                import hashlib
                def _sha256_file(path: Path) -> str:
                    h = hashlib.sha256()
                    with path.open("rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            h.update(chunk)
                    return h.hexdigest()
                checksum = _sha256_file(p)

            # Optionally analyze media metadata to backfill Track.duration_ms when missing
            actual_duration_ms = None
            if analyze_metadata:
                try:
                    from sqlalchemy import select as _select
                    # Fetch track to check/update duration
                    t_res = await session.execute(_select(Track).where(Track.id == track_id))
                    t = t_res.scalars().first()
                    # Run ffprobe to get actual duration from file
                    import subprocess, json
                    cmd = [
                        "ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "format=duration", "-of", "json", str(p)
                    ]
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if proc.returncode == 0 and proc.stdout:
                            data = json.loads(proc.stdout)
                            # ffprobe might return duration under format.duration (string)
                            dur = None
                            if isinstance(data, dict):
                                fmt = data.get("format") or {}
                                d = fmt.get("duration")
                                if isinstance(d, str):
                                    try:
                                        dur = float(d)
                                    except Exception:
                                        dur = None
                            if dur and dur > 0:
                                actual_duration_ms = int(dur * 1000)
                                # Also backfill Track.duration_ms if missing
                                if t and (t.duration_ms is None or t.duration_ms == 0):
                                    t.duration_ms = actual_duration_ms
                                    # Flush to persist update alongside LibraryFile upserts
                                    await session.flush()
                    except Exception:
                        # Ignore ffprobe failures; proceed without duration
                        pass
                except Exception:
                    # If model imports fail in alternate run modes, skip metadata.
                    pass

            res = await session.execute(_select(LibraryFile).where(LibraryFile.filepath == str(p)))
            lf = res.scalars().first()
            if lf:
                lf.track_id = track_id
                lf.file_mtime = mtime
                lf.file_size = size
                if compute_checksum:
                    lf.checksum_sha256 = checksum
                lf.exists = True
                if actual_duration_ms is not None:
                    lf.actual_duration_ms = actual_duration_ms
                updated += 1
            else:
                lf = LibraryFile(
                    track_id=track_id,
                    filepath=str(p),
                    file_mtime=mtime,
                    file_size=size,
                    checksum_sha256=checksum,
                    exists=True,
                    actual_duration_ms=actual_duration_ms,
                )
                session.add(lf)
                added += 1
    await session.flush()
    return {
        "ok": True,
        "directory": str(lib_dir),
        "scanned": scanned,
        "matched": matched,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "skipped_files": skipped_files,
    }


@router.post("/reindex_from_tracks", tags=["library"], summary="Verify DB tracks against library and upsert LibraryFile entries")
async def reindex_from_tracks(
    session: AsyncSession = Depends(get_session),
    link: bool = Query(True, description="When true, create/update LibraryFile rows for found files."),
    compute_checksum: bool = Query(False, description="Compute checksum_sha256 for newly linked files (slower)"),
):
    """Reverse reindex: Build an index of files on disk by normalized (artists, title),
    then iterate DB Tracks to check presence and optionally (link) upsert LibraryFile entries.

    Returns summary with found/missing counts and a sample of missing tracks.
    """
    try:
        from ...db.models.models import LibraryFile  # type: ignore
        from sqlalchemy import select as _select
    except Exception:  # pragma: no cover
        from db.models.models import LibraryFile  # type: ignore
        from sqlalchemy import select as _select

    lib_dir = Path(os.environ.get("LIBRARY_DIR") or settings.library_dir).resolve()
    if not lib_dir.exists() or not lib_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Library directory not found: {lib_dir}")

    # Build index of files by normalized key
    file_index: Dict[Tuple[str, str], List[Path]] = {}
    total_files = 0
    for root, _, files in os.walk(lib_dir):
        for fn in files:
            p = Path(root) / fn
            if not _is_audio_file(p):
                continue
            total_files += 1
            key = _normalized_key_from_filename(p.name)
            if not key:
                continue
            file_index.setdefault(key, []).append(p)

    # Fetch all tracks
    t_res = await session.execute(select(Track))
    tracks = t_res.scalars().all()

    checked = 0
    found = 0
    missing = 0
    linked_added = 0
    linked_updated = 0
    missing_samples: List[dict] = []

    for t in tracks:
        checked += 1
        key = (t.normalized_artists, t.normalized_title)
        candidates = file_index.get(key) or []
        if not candidates:
            missing += 1
            # Collect small sample (up to 20) for UI
            if len(missing_samples) < 20:
                missing_samples.append({
                    "id": t.id,
                    "artists": t.artists,
                    "title": t.title,
                    "normalized_artists": t.normalized_artists,
                    "normalized_title": t.normalized_title,
                })
            continue
        found += 1
        if not link:
            continue
        # Link the first candidate path; users can rescan for others
        p = candidates[0]
        try:
            st = p.stat()
            mtime = datetime.utcfromtimestamp(st.st_mtime)
            size = int(st.st_size)
        except Exception:
            mtime = datetime.utcnow()
            size = 0

        checksum = None
        if compute_checksum:
            import hashlib
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            checksum = h.hexdigest()

        # Upsert LibraryFile by filepath
        res = await session.execute(_select(LibraryFile).where(LibraryFile.filepath == str(p)))
        lf = res.scalars().first()
        if lf:
            # Update linkage/metadata
            lf.track_id = t.id
            lf.file_mtime = mtime
            lf.file_size = size
            if compute_checksum:
                lf.checksum_sha256 = checksum
            lf.exists = True
            linked_updated += 1
        else:
            lf = LibraryFile(
                track_id=t.id,
                filepath=str(p),
                file_mtime=mtime,
                file_size=size,
                checksum_sha256=checksum,
                exists=True,
            )
            session.add(lf)
            linked_added += 1

    await session.flush()
    return {
        "ok": True,
        "directory": str(lib_dir),
        "files_indexed": total_files,
        "tracks_checked": checked,
        "tracks_found": found,
        "tracks_missing": missing,
        "linked_added": linked_added,
        "linked_updated": linked_updated,
        "missing_samples": missing_samples,
    }


# Add a new router for streaming by track_id
stream_router = APIRouter(prefix="/library", tags=["library"])

@stream_router.get("/stream/{track_id}")
async def stream_by_track_id(track_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    """Stream the first available library file for a track with HTTP Range support.
    
    - Finds the first library file associated with the track
    - Delegates to the same streaming logic as stream_library_file
    - Returns 404 if no file found for the track
    """
    # Find the first library file for this track
    stmt = select(LibraryFile).where(
        and_(
            LibraryFile.track_id == track_id,
            LibraryFile.exists == True
        )
    ).limit(1)
    
    result = await session.execute(stmt)
    library_file = result.scalar_one_or_none()
    
    if not library_file:
        raise HTTPException(status_code=404, detail="No audio file found for this track")
    
    # Use the existing streaming logic
    if not library_file.filepath:
        raise HTTPException(status_code=404, detail="File path is missing")
    
    path = Path(library_file.filepath)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    # Get file stats for headers
    stat = path.stat()
    file_size = stat.st_size
    last_modified = formatdate(stat.st_mtime, usegmt=True)
    etag = f'"{stat.st_mtime}-{file_size}"'
    
    # Parse Range header if present
    range_header = request.headers.get('range')
    if range_header:
        try:
            ranges = parse_http_range(range_header, file_size)
            if ranges and len(ranges) == 1:
                start, end = ranges[0]
                content_length = end - start + 1
                
                def iter_file_range():
                    with open(path, 'rb') as f:
                        f.seek(start)
                        remaining = content_length
                        while remaining > 0:
                            chunk_size = min(8192, remaining)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            yield chunk
                
                headers = {
                    'Content-Range': build_content_range_header(start, end, file_size),
                    'Content-Length': str(content_length),
                    'Accept-Ranges': 'bytes',
                    'Content-Type': pick_audio_mime_from_path(path),
                    'ETag': etag,
                    'Last-Modified': last_modified,
                    'Cache-Control': 'public, max-age=3600',
                }
                
                return StreamingResponse(
                    iter_file_range(),
                    status_code=206,
                    headers=headers
                )
        except Exception:
            pass  # Fall back to full file response
    
    # Full file response
    headers = {
        'Content-Length': str(file_size),
        'Accept-Ranges': 'bytes',
        'Content-Type': pick_audio_mime_from_path(path),
        'ETag': etag,
        'Last-Modified': last_modified,
        'Cache-Control': 'public, max-age=3600',
    }
    
    def iter_file():
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk
    
    return StreamingResponse(
        iter_file(),
        status_code=200,
        headers=headers
    )


@router.post("/verify_and_organize_playlists", tags=["library"], summary="Verify and organize all downloaded tracks into playlist folders")
async def verify_and_organize_playlists(session: AsyncSession = Depends(get_session)):
    """
    For all tracks with completed downloads:
    1. Verify files exist in correct playlist folders
    2. Create missing copies for tracks in multiple playlists
    3. Report file size conflicts
    
    Returns detailed report of actions taken and issues found.
    """
    from sqlalchemy import select as _select
    try:
        from ...db.models.models import Download, Playlist, PlaylistTrack  # type: ignore
        from ...utils.downloader import _sanitize_component  # type: ignore
    except Exception:  # pragma: no cover
        from db.models.models import Download, Playlist, PlaylistTrack  # type: ignore
        from utils.downloader import _sanitize_component  # type: ignore
    
    # Get library directory
    lib_dir = Path(os.environ.get("LIBRARY_DIR") or settings.library_dir).resolve()
    
    # Get all tracks that have at least one existing library file
    # This is more reliable than checking Download status
    library_file_stmt = (
        _select(LibraryFile.track_id)
        .where(LibraryFile.exists == True)  # noqa: E712
        .distinct()
    )
    library_file_result = await session.execute(library_file_stmt)
    track_ids_with_files = set(row[0] for row in library_file_result.all())
    
    if not track_ids_with_files:
        return {
            "total_tracks_checked": 0,
            "files_verified": 0,
            "files_created": 0,
            "files_missing": 0,
            "size_conflicts": [],
            "errors": []
        }
    
    files_verified = 0
    files_created = 0
    files_missing = 0
    size_conflicts = []
    errors = []
    
    for track_id in track_ids_with_files:
        try:
            # Get track details
            track = await session.get(Track, track_id)
            if not track:
                continue
            
            # Get all playlists for this track
            playlist_stmt = (
                _select(Playlist)
                .join(PlaylistTrack)
                .where(PlaylistTrack.track_id == track_id)
            )
            playlist_result = await session.execute(playlist_stmt)
            playlists = playlist_result.scalars().all()
            
            if not playlists:
                # Track has download but no playlists - orphaned
                errors.append({
                    "track_id": track_id,
                    "track_title": f"{track.artists} - {track.title}",
                    "error": "Track has completed download but no playlist memberships"
                })
                continue
            
            # Get existing library files for this track
            lf_stmt = _select(LibraryFile).where(
                LibraryFile.track_id == track_id,
                LibraryFile.exists == True  # noqa: E712
            )
            lf_result = await session.execute(lf_stmt)
            existing_library_files = lf_result.scalars().all()
            
            # Build map of existing files by path
            existing_files_map = {}
            for lf in existing_library_files:
                if lf.filepath and Path(lf.filepath).exists():
                    existing_files_map[lf.filepath] = lf.file_size
            
            if not existing_files_map:
                files_missing += len(playlists)
                errors.append({
                    "track_id": track_id,
                    "track_title": f"{track.artists} - {track.title}",
                    "error": f"No files found on disk (expected in {len(playlists)} playlist(s))"
                })
                continue
            
            # Build filename
            artists_str = _sanitize_component(track.artists or "Unknown Artist")
            title_str = _sanitize_component(track.title or "Unknown Title")
            
            # Determine extension from existing files
            existing_extensions = set()
            for filepath in existing_files_map.keys():
                ext = Path(filepath).suffix
                if ext:
                    existing_extensions.add(ext)
            
            if not existing_extensions:
                errors.append({
                    "track_id": track_id,
                    "track_title": f"{track.artists} - {track.title}",
                    "error": "Could not determine file extension"
                })
                continue
            
            # Use the first found extension (should be same for all)
            ext = list(existing_extensions)[0]
            filename = f"{artists_str} - {title_str}{ext}"
            
            # Check if multiple different file sizes exist
            unique_sizes = set(existing_files_map.values())
            if len(unique_sizes) > 1:
                size_conflicts.append({
                    "track_id": track_id,
                    "track_title": f"{track.artists} - {track.title}",
                    "files": [
                        {"path": path, "size": size}
                        for path, size in existing_files_map.items()
                    ]
                })
            
            # Get a source file for copying (use the largest if multiple sizes)
            source_file = None
            source_size = 0
            for filepath, size in existing_files_map.items():
                if size > source_size:
                    source_file = Path(filepath)
                    source_size = size
            
            if not source_file or not source_file.exists():
                continue
            
            # Verify/create file in each playlist folder
            for playlist in playlists:
                try:
                    provider_folder = _sanitize_component(
                        playlist.provider.value if hasattr(playlist.provider, 'value') else str(playlist.provider)
                    )
                    playlist_folder = _sanitize_component(playlist.name)
                    
                    target_dir = lib_dir / provider_folder / playlist_folder
                    target_path = target_dir / filename
                    
                    # Check if file already exists
                    if str(target_path) in existing_files_map:
                        files_verified += 1
                        continue
                    
                    # File missing - create it
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(source_file, target_path)
                    files_created += 1
                    
                    # Create LibraryFile entry
                    try:
                        st = target_path.stat()
                        new_lf = LibraryFile(
                            track_id=track_id,
                            filepath=str(target_path),
                            file_mtime=datetime.utcfromtimestamp(st.st_mtime),
                            file_size=int(st.st_size),
                            exists=True,
                        )
                        session.add(new_lf)
                    except Exception as e:
                        errors.append({
                            "track_id": track_id,
                            "track_title": f"{track.artists} - {track.title}",
                            "error": f"Failed to create LibraryFile entry for {target_path}: {str(e)}"
                        })
                        
                except Exception as e:
                    errors.append({
                        "track_id": track_id,
                        "track_title": f"{track.artists} - {track.title}",
                        "error": f"Failed to verify/create file in playlist {playlist.name}: {str(e)}"
                    })
                    
        except Exception as e:
            errors.append({
                "track_id": track_id,
                "track_title": "Unknown",
                "error": f"Failed to process track: {str(e)}"
            })
    
    await session.commit()
    
    return {
        "total_tracks_checked": len(track_ids_with_files),
        "files_verified": files_verified,
        "files_created": files_created,
        "files_missing": files_missing,
        "size_conflicts": size_conflicts,
        "errors": errors
    }

