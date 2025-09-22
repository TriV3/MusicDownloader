from __future__ import annotations

from datetime import datetime
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

try:  # package mode
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Download, DownloadStatus, DownloadProvider, Track, SearchCandidate, LibraryFile  # type: ignore
    from ...schemas.models import DownloadRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Download, DownloadStatus, DownloadProvider, Track, SearchCandidate, LibraryFile  # type: ignore
    from schemas.models import DownloadRead  # type: ignore


router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.get("/", response_model=List[DownloadRead])
async def list_downloads(
    session: AsyncSession = Depends(get_session),
    status: Optional[DownloadStatus] = Query(None),
    track_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    conds = []
    if status is not None:
        conds.append(Download.status == status)
    if track_id is not None:
        conds.append(Download.track_id == track_id)
    stmt = select(Download)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(desc(Download.created_at)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.scalars().all()


# Accept both with and without trailing slash
@router.get("", response_model=List[DownloadRead])
async def list_downloads_no_slash(
    session: AsyncSession = Depends(get_session),
    status: Optional[DownloadStatus] = Query(None),
    track_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return await list_downloads(session=session, status=status, track_id=track_id, limit=limit, offset=offset)


@router.get("/with_tracks", response_model=List[dict])
async def list_downloads_with_tracks(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return downloads enriched with track artists/title for UI convenience."""
    stmt = (
        select(Download, Track)
        .join(Track, Download.track_id == Track.id)
        .order_by(desc(Download.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict] = []
    for d, t in rows:
        out.append({
            "id": d.id,
            "track_id": d.track_id,
            "candidate_id": d.candidate_id,
            "provider": d.provider,
            "status": d.status,
            "filepath": d.filepath,
            "format": d.format,
            "bitrate_kbps": d.bitrate_kbps,
            "filesize_bytes": d.filesize_bytes,
            "checksum_sha256": d.checksum_sha256,
            "error_message": d.error_message,
            "started_at": d.started_at,
            "finished_at": d.finished_at,
            "created_at": d.created_at,
            # Enrichment
            "track_title": t.title,
            "track_artists": t.artists,
        })
    # Ensure all datetimes/enums are JSON-serializable
    return JSONResponse(content=jsonable_encoder(out))


@router.get("/{download_id}", response_model=DownloadRead)
async def get_download(download_id: int, session: AsyncSession = Depends(get_session)):
    item = await session.get(Download, download_id)
    if not item:
        raise HTTPException(status_code=404, detail="Download not found")
    return item


@router.post("/enqueue", response_model=DownloadRead)
async def enqueue_download(
    track_id: int,
    candidate_id: Optional[int] = None,
    provider: DownloadProvider = DownloadProvider.yt_dlp,
    force: bool = Query(False, description="Bypass duplicate prevention to force download"),
    session: AsyncSession = Depends(get_session),
):
    # Validate references exist
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    cand = None
    if candidate_id is not None:
        cand = await session.get(SearchCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")
        if cand.track_id != track_id:
            raise HTTPException(status_code=400, detail="Candidate does not belong to track")

    # Duplicate prevention: if a library file already exists for this track (and on disk),
    # or a prior successful download produced a file that still exists, return an "already" item.
    existing_path: Optional[str] = None
    try:
        # Prefer LibraryFile rows (they reflect current disk presence via exists flag)
        lib_stmt = (
            select(LibraryFile)
            .where(LibraryFile.track_id == track_id)
            .order_by(desc(LibraryFile.file_mtime))
        )
        lib_res = await session.execute(lib_stmt)
        lib_row = lib_res.scalars().first()
        if lib_row and lib_row.filepath and os.path.exists(lib_row.filepath):
            existing_path = lib_row.filepath
        else:
            # Fallback: latest successful download with a filepath that exists
            done_stmt = (
                select(Download)
                .where(
                    and_(
                        Download.track_id == track_id,
                        Download.status == DownloadStatus.done,
                        Download.filepath.is_not(None),
                    )
                )
                .order_by(desc(Download.finished_at))
            )
            done_res = await session.execute(done_stmt)
            prev_done = done_res.scalars().first()
            if prev_done and prev_done.filepath and os.path.exists(prev_done.filepath):
                existing_path = prev_done.filepath
    except Exception:
        # Best-effort; if anything goes wrong, proceed with normal enqueue
        existing_path = None

    if existing_path and not force:
        dl = Download(
            track_id=track_id,
            candidate_id=candidate_id,
            provider=provider,
            status=DownloadStatus.already,
            filepath=existing_path,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
        )
        session.add(dl)
        await session.flush()
        try:
            await session.commit()
        except Exception:
            pass
        # Do not enqueue to worker — we already have the file
        return dl

    dl = Download(
        track_id=track_id,
        candidate_id=candidate_id,
        provider=provider,
        status=DownloadStatus.queued,
        created_at=datetime.utcnow(),
    )
    session.add(dl)
    await session.flush()
    # Ensure the row is committed before the worker (separate session) tries to read it
    try:
        await session.commit()
    except Exception:
        # let dependency rollback/commit handle, but attempt enqueue regardless
        pass
    # Push to in-memory queue if worker is running
    try:  # pragma: no cover
        from ...worker import downloads_worker as dw  # type: ignore
        if dw.download_queue:
            await dw.download_queue.enqueue(dl.id)
    except Exception:
        pass
    return dl


@router.post("/cancel/{download_id}", response_model=DownloadRead)
async def cancel_download(download_id: int, session: AsyncSession = Depends(get_session)):
    dl = await session.get(Download, download_id)
    if not dl:
        raise HTTPException(status_code=404, detail="Download not found")
    if dl.status == DownloadStatus.running:
        raise HTTPException(status_code=409, detail="Cannot cancel a running download")
    if dl.status in {DownloadStatus.done, DownloadStatus.failed, DownloadStatus.skipped, DownloadStatus.already}:
        return dl
    dl.status = DownloadStatus.skipped
    dl.finished_at = datetime.utcnow()
    await session.flush()
    # Note: If the job was enqueued already, worker will skip when it sees status=skipped.
    return dl


# Test-only helpers (not included in OpenAPI docs)
class _WorkerRestartBody(BaseModel):
    concurrency: int = 2
    simulate_seconds: float = 0.1


@router.post("/_restart_worker", include_in_schema=False)
async def restart_worker(payload: _WorkerRestartBody):
    try:  # pragma: no cover
        from ...worker import downloads_worker as dw  # type: ignore
    except Exception:  # pragma: no cover
        from worker import downloads_worker as dw  # type: ignore
    try:
        if dw.download_queue:
            await dw.download_queue.stop()
    except Exception:
        pass
    concurrency = max(1, int(payload.concurrency))
    try:
        simulate_seconds = float(payload.simulate_seconds)
    except Exception:
        simulate_seconds = 0.0
    dw.download_queue = dw.DownloadQueue(concurrency=concurrency, simulate_seconds=simulate_seconds)
    await dw.download_queue.start()
    return {"ok": True, "concurrency": concurrency, "simulate_seconds": simulate_seconds}


@router.post("/_wait_idle", include_in_schema=False)
async def wait_idle(timeout: float = 3.0, track_id: Optional[int] = None, stop_after: bool = False):
    try:  # pragma: no cover
        from ...worker import downloads_worker as dw  # type: ignore
    except Exception:  # pragma: no cover
        from worker import downloads_worker as dw  # type: ignore
    if dw.download_queue:
        await dw.download_queue.wait_idle(timeout=timeout)
        # Optionally also wait for DB to reflect terminal states
        if track_id is not None:
            import asyncio
            from sqlalchemy import select
            from ...db.session import async_session  # type: ignore
            terminal = {DownloadStatus.done, DownloadStatus.failed, DownloadStatus.skipped, DownloadStatus.already}
            end = asyncio.get_event_loop().time() + timeout
            while True:
                async with async_session() as session:
                    result = await session.execute(select(Download).where(Download.track_id == track_id))
                    rows = result.scalars().all()
                if rows and all(r.status in terminal for r in rows):
                    break
                if asyncio.get_event_loop().time() > end:
                    break
                await asyncio.sleep(0.05)
        if stop_after:
            try:
                await dw.download_queue.stop()
            finally:
                dw.download_queue = None
            return {"ok": True, "stopped": True}
        qsize = getattr(getattr(dw.download_queue, "queue", None), "qsize", lambda: 0)()
        tasks = len(getattr(dw.download_queue, "_tasks", []) or [])
        return {"ok": True, "qsize": qsize, "tasks": tasks}
    return {"ok": False}
