from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:  # package mode
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Playlist, Track, PlaylistTrack  # type: ignore
    from ...schemas.models import PlaylistTrackCreate, PlaylistTrackRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Playlist, Track, PlaylistTrack  # type: ignore
    from schemas.models import PlaylistTrackCreate, PlaylistTrackRead  # type: ignore


router = APIRouter(prefix="/playlist_tracks", tags=["playlists"])


@router.post("/", response_model=PlaylistTrackRead)
async def create_playlist_track(
    payload: PlaylistTrackCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create or update a link between a playlist and a track.

    Idempotent: if the link already exists, updates optional fields (position, added_at).
    """
    playlist = await session.get(Playlist, payload.playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    track = await session.get(Track, payload.track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    result = await session.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.playlist_id == payload.playlist_id,
            PlaylistTrack.track_id == payload.track_id,
        )
    )
    link: Optional[PlaylistTrack] = result.scalars().first()
    if not link:
        link = PlaylistTrack(
            playlist_id=payload.playlist_id,
            track_id=payload.track_id,
            position=payload.position,
            added_at=payload.added_at,
        )
        session.add(link)
        await session.flush()
    else:
        if payload.position is not None:
            link.position = payload.position
        if payload.added_at is not None:
            link.added_at = payload.added_at
        await session.flush()
    return link
