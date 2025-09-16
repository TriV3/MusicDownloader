from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

try:  # package mode
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Download, DownloadStatus, DownloadProvider, Track, SearchCandidate  # type: ignore
    from ...schemas.models import DownloadRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Download, DownloadStatus, DownloadProvider, Track, SearchCandidate  # type: ignore
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


# Test-only helpers (not included in OpenAPI docs)
@router.post("/_restart_worker", include_in_schema=False)
async def restart_worker(concurrency: int = 2, simulate_seconds: float = 0.1):
    try:  # pragma: no cover
        from ...worker import downloads_worker as dw  # type: ignore
    except Exception:  # pragma: no cover
        from worker import downloads_worker as dw  # type: ignore
    try:
        if dw.download_queue:
            await dw.download_queue.stop()
    except Exception:
        pass
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
