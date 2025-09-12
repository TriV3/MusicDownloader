from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

try:  # package mode
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import TrackIdentity, Track  # type: ignore
    from ...schemas.models import (
        TrackIdentityCreate,
        TrackIdentityRead,
    )  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import TrackIdentity, Track  # type: ignore
    from schemas.models import (
        TrackIdentityCreate,
        TrackIdentityRead,
    )  # type: ignore


router = APIRouter(prefix="/identities", tags=["identities"])


@router.get("/", response_model=List[TrackIdentityRead])
async def list_identities(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    has_fingerprint: Optional[bool] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
):
    conds = []
    if track_id is not None:
        conds.append(TrackIdentity.track_id == track_id)
    if has_fingerprint is not None:
        if has_fingerprint:
            conds.append(TrackIdentity.fingerprint.is_not(None))
        else:
            conds.append(TrackIdentity.fingerprint.is_(None))
    if created_from is not None:
        conds.append(TrackIdentity.created_at >= created_from)
    if created_to is not None:
        conds.append(TrackIdentity.created_at <= created_to)
    stmt = select(TrackIdentity)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(TrackIdentity.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=TrackIdentityRead)
async def create_identity(payload: TrackIdentityCreate, session: AsyncSession = Depends(get_session)):
    # ensure track exists
    track = await session.get(Track, payload.track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    identity = TrackIdentity(**payload.model_dump())
    session.add(identity)
    await session.flush()
    return identity


@router.get("/{identity_id}", response_model=TrackIdentityRead)
async def get_identity(identity_id: int, session: AsyncSession = Depends(get_session)):
    identity = await session.get(TrackIdentity, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    return identity


@router.put("/{identity_id}", response_model=TrackIdentityRead)
async def update_identity(identity_id: int, payload: TrackIdentityCreate, session: AsyncSession = Depends(get_session)):
    identity = await session.get(TrackIdentity, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    for k, v in payload.model_dump().items():
        setattr(identity, k, v)
    await session.flush()
    return identity


@router.delete("/{identity_id}")
async def delete_identity(identity_id: int, session: AsyncSession = Depends(get_session)):
    identity = await session.get(TrackIdentity, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    await session.delete(identity)
    return {"deleted": True}
