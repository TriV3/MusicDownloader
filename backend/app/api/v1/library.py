from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import platform
import subprocess

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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(LibraryFile)
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
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return await list_library_files(session=session, track_id=track_id, limit=limit, offset=offset)


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
