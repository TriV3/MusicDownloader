from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Playlist  # type: ignore
    from ...schemas.models import PlaylistCreate, PlaylistRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Playlist  # type: ignore
    from schemas.models import PlaylistCreate, PlaylistRead  # type: ignore


router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("/", response_model=List[PlaylistRead])
async def list_playlists(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Playlist))
    return result.scalars().all()


@router.post("/", response_model=PlaylistRead)
async def create_playlist(payload: PlaylistCreate, session: AsyncSession = Depends(get_session)):
    playlist = Playlist(**payload.model_dump())
    session.add(playlist)
    await session.flush()
    return playlist


@router.get("/{playlist_id}", response_model=PlaylistRead)
async def get_playlist(playlist_id: int, session: AsyncSession = Depends(get_session)):
    playlist = await session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist
