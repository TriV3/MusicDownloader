from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Track, TrackIdentity, SourceProvider  # type: ignore
    from ...schemas.models import TrackCreate, TrackRead  # type: ignore
    from ...utils.normalize import normalize_track  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Track, TrackIdentity, SourceProvider  # type: ignore
    from schemas.models import TrackCreate, TrackRead  # type: ignore
    from utils.normalize import normalize_track  # type: ignore


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
    # Auto-create a manual identity if none exists yet
    identity = TrackIdentity(
        track_id=track.id,
        provider=SourceProvider.manual,
        provider_track_id=f"manual:{track.id}",
        provider_url=None,
    )
    session.add(identity)
    await session.flush()
    return track


@router.get("/{track_id}", response_model=TrackRead)
async def get_track(track_id: int, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track


@router.put("/{track_id}", response_model=TrackRead)
async def update_track(track_id: int, payload: TrackCreate, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    for k, v in payload.model_dump().items():
        setattr(track, k, v)
    # Example propagation: update updated_at on identities (SQLAlchemy onupdate handles, but we force a change)
    identities = track.identities if hasattr(track, 'identities') else []  # type: ignore[attr-defined]
    for ident in identities:
        # Placeholder for future logic (e.g., regenerate fingerprint). Force updated_at by touching field.
        ident.provider_url = ident.provider_url  # no-op assignment
    await session.flush()
    return track


@router.get("/normalize/preview")
async def preview_normalization(
    artists: str = Query("", description="Original artists string"),
    title: str = Query("", description="Original title string"),
):
    """Return normalized fields and flags for a given artist/title pair."""
    result = normalize_track(artists, title)
    return {
        "primary_artist": result.primary_artist,
        "clean_artists": result.clean_artists,
        "clean_title": result.clean_title,
        "normalized_artists": result.normalized_artists,
        "normalized_title": result.normalized_title,
        "is_remix_or_edit": result.is_remix_or_edit,
        "is_live": result.is_live,
        "is_remaster": result.is_remaster,
    }
