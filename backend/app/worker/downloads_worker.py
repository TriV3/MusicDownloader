from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    from ..db.session import async_session  # type: ignore
    from ..db.models.models import Download, DownloadStatus  # type: ignore
except Exception:  # pragma: no cover
    from db.session import async_session  # type: ignore
    from db.models.models import Download, DownloadStatus  # type: ignore


@dataclass
class DownloadJob:
    download_id: int


class DownloadQueue:
    def __init__(self, concurrency: int = 2, simulate_seconds: float = 0.3) -> None:
        self.queue: asyncio.Queue[DownloadJob] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self.concurrency = max(1, concurrency)
        self.simulate_seconds = simulate_seconds
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        self._stopped.clear()
        for _ in range(self.concurrency):
            self._tasks.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        self._stopped.set()
        # Wake any waiting getters so loops can notice the stop flag quickly
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed():
                for _ in self._tasks:
                    with contextlib.suppress(Exception):
                        self.queue.put_nowait(DownloadJob(download_id=-1))
        except Exception:
            pass
        # Wait briefly for graceful exit, then cancel as a fallback
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=0.5)
        for t in self._tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def enqueue(self, download_id: int) -> None:
        await self.queue.put(DownloadJob(download_id))
        # No-op return; tests may rely on join() to wait until processed

    async def _worker_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                job = await asyncio.wait_for(self.queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process_job(job)
            finally:
                with contextlib.suppress(Exception):
                    self.queue.task_done()

    async def wait_idle(self, timeout: float = 2.0) -> None:
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def _process_job(self, job: DownloadJob) -> None:
        print(f"[worker] Starting job for download_id={job.download_id}")
        # Update status -> running
        async with async_session() as session:
            dl = await session.get(Download, job.download_id)
            if not dl:
                print(f"[worker] Download row not found id={job.download_id}")
                return
            if dl.status not in (DownloadStatus.queued, DownloadStatus.failed):
                print(f"[worker] Skipping download id={job.download_id} with status={dl.status}")
                return
            dl.status = DownloadStatus.running
            dl.started_at = datetime.utcnow()
            await session.flush()
            await session.commit()

        # Execute real download or simulate
        try:
            if self.simulate_seconds and self.simulate_seconds > 0:
                print(f"[worker] Simulating download for id={job.download_id} seconds={self.simulate_seconds}")
                await asyncio.sleep(self.simulate_seconds)
                outcome = None
            else:
                from ..utils.downloader import perform_download  # type: ignore
                outcome = await perform_download(job.download_id)

            # Mark done and persist outcome
            async with async_session() as session:
                dl = await session.get(Download, job.download_id)
                if not dl:
                    return
                if outcome is not None:
                    dl.filepath = str(outcome.filepath)
                    dl.format = outcome.format
                    dl.filesize_bytes = outcome.filesize_bytes
                    dl.checksum_sha256 = outcome.checksum_sha256
                else:
                    print(f"[worker] No outcome produced for id={job.download_id} (simulate or error earlier)")
                dl.status = DownloadStatus.done
                dl.finished_at = datetime.utcnow()
                # Upsert LibraryFile entry for this track/path
                try:
                    from ..db.models.models import LibraryFile  # type: ignore
                    from pathlib import Path
                    if dl.filepath:
                        p = Path(dl.filepath)
                        try:
                            st = p.stat()
                            mtime = datetime.utcfromtimestamp(st.st_mtime)
                            size = int(st.st_size)
                        except Exception:
                            mtime = datetime.utcnow()
                            size = dl.filesize_bytes or 0
                        # Try find existing by unique filepath
                        from sqlalchemy import select as _select
                        res = await session.execute(_select(LibraryFile).where(LibraryFile.filepath == str(p)))
                        lf = res.scalars().first()
                        if lf:
                            lf.track_id = dl.track_id
                            lf.file_mtime = mtime
                            lf.file_size = size
                            lf.checksum_sha256 = dl.checksum_sha256
                            lf.exists = True
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
                except Exception as _e:
                    print(f"[worker] Failed to upsert LibraryFile for id={job.download_id}: {_e}")
                # If the track has no cover yet, set it from the YouTube candidate (or chosen YouTube) thumbnail
                try:
                    from ..db.models.models import Track as _Track, SearchCandidate as _SC, SearchProvider as _SP  # type: ignore
                    from ..utils.images import youtube_thumbnail_url as _yt_thumb  # type: ignore
                    # Re-load track for fresh state
                    tr = await session.get(_Track, dl.track_id)
                    if tr:
                        thumb_url = None
                        cand: Optional[_SC] = None
                        if dl.candidate_id:
                            cand = await session.get(_SC, dl.candidate_id)
                        if cand and cand.provider == _SP.youtube:
                            thumb_url = _yt_thumb(cand.external_id) or _yt_thumb(cand.url)
                        if not thumb_url:
                            from sqlalchemy import select as _select, desc as _desc
                            res2 = await session.execute(
                                _select(_SC)
                                .where(_SC.track_id == dl.track_id, _SC.provider == _SP.youtube)
                                .order_by(_desc(_SC.score))
                            )
                            yc = res2.scalars().first()
                            if yc:
                                thumb_url = _yt_thumb(yc.external_id) or _yt_thumb(yc.url)
                        # Update if missing or different
                        if thumb_url and (not tr.cover_url or tr.cover_url != thumb_url):
                            tr.cover_url = thumb_url
                except Exception as _e:
                    print(f"[worker] Failed to set cover for track {dl.track_id}: {_e}")
                await session.flush()
                await session.commit()
                print(f"[worker] Completed download id={job.download_id} -> {dl.filepath}")
        except Exception as e:
            async with async_session() as session:
                dl = await session.get(Download, job.download_id)
                if not dl:
                    return
                dl.status = DownloadStatus.failed
                dl.finished_at = datetime.utcnow()
                dl.error_message = str(e) or "Worker error"
                await session.flush()
                await session.commit()
            print(f"[worker] Failed download id={job.download_id}: {e}")


# Singleton queue instance (managed by app startup/shutdown)
download_queue: Optional[DownloadQueue] = None
