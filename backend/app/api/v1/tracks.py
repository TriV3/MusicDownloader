from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Track  # type: ignore
    from ...schemas.models import TrackCreate, TrackRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Track  # type: ignore
    from schemas.models import TrackCreate, TrackRead  # type: ignore


router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/", response_model=List[TrackRead])
async def list_tracks(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Track))
    return result.scalars().all()


@router.post("/", response_model=TrackRead)
async def create_track(payload: TrackCreate, session: AsyncSession = Depends(get_session)):
    track = Track(**payload.model_dump())
    session.add(track)
    await session.flush()
    return track


@router.get("/{track_id}", response_model=TrackRead)
async def get_track(track_id: int, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track
