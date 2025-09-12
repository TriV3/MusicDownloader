from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import (
        Track,
        TrackIdentity,
        SourceProvider,
        SearchCandidate,
        Download,
        PlaylistTrack,
        LibraryFile,
    )  # type: ignore
    from ...schemas.models import TrackCreate, TrackRead  # type: ignore
    from ...utils.normalize import normalize_track  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import (
        Track,
        TrackIdentity,
        SourceProvider,
        SearchCandidate,
        Download,
        PlaylistTrack,
        LibraryFile,
    )  # type: ignore
    from schemas.models import TrackCreate, TrackRead  # type: ignore
    from utils.normalize import normalize_track  # type: ignore


router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/", response_model=List[TrackRead])
async def list_tracks(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Track))
    return result.scalars().all()


@router.post("/", response_model=TrackRead)
async def create_track(payload: TrackCreate, session: AsyncSession = Depends(get_session)):
    data = payload.model_dump()
    # Auto-normalize if missing
    if not data.get("normalized_title") or not data.get("normalized_artists"):
        norm = normalize_track(data["artists"], data["title"],)
        data["normalized_artists"] = norm.normalized_artists
        data["normalized_title"] = norm.normalized_title
    track = Track(**data)
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


@router.delete("/{track_id}", status_code=204)
async def delete_track(track_id: int, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    # Manually cascade delete dependent rows (SQLite without FK cascades enabled by default here)
    await session.execute(delete(TrackIdentity).where(TrackIdentity.track_id == track_id))
    await session.execute(delete(SearchCandidate).where(SearchCandidate.track_id == track_id))
    await session.execute(delete(Download).where(Download.track_id == track_id))
    await session.execute(delete(PlaylistTrack).where(PlaylistTrack.track_id == track_id))
    await session.execute(delete(LibraryFile).where(LibraryFile.track_id == track_id))
    await session.delete(track)
    await session.flush()
    return None


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
    data = payload.model_dump()
    title_changed = data.get("title") and data["title"] != track.title
    artists_changed = data.get("artists") and data["artists"] != track.artists
    if (title_changed or artists_changed) and (not data.get("normalized_title") or not data.get("normalized_artists")):
        norm = normalize_track(data.get("artists", track.artists), data.get("title", track.title))
        data.setdefault("normalized_artists", norm.normalized_artists)
        data.setdefault("normalized_title", norm.normalized_title)
    for k, v in data.items():
        setattr(track, k, v)
    # Touch identities to bump updated_at (placeholder for future logic)
    identities = getattr(track, 'identities', [])  # type: ignore[attr-defined]
    for ident in identities:
        ident.provider_url = ident.provider_url
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
