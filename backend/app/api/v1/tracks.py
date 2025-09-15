from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, desc
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
    from ...schemas.models import TrackCreate, TrackRead, SearchCandidateRead  # type: ignore
    from ...utils.normalize import normalize_track, duration_delta_sec  # type: ignore
    from ...utils.youtube_search import search_youtube  # type: ignore
    from ...db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from ...core.config import settings  # type: ignore
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
    from schemas.models import TrackCreate, TrackRead, SearchCandidateRead  # type: ignore
    from utils.normalize import normalize_track, duration_delta_sec  # type: ignore
    from utils.youtube_search import search_youtube  # type: ignore
    from db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from core.config import settings  # type: ignore


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


@router.get("/{track_id}/youtube/search", response_model=List[SearchCandidateRead])
async def youtube_search_track(
    track_id: int,
    session: AsyncSession = Depends(get_session),
    prefer_extended: bool = Query(False, description="Prefer Extended/Club Mix variants"),
    persist: bool = Query(True, description="Persist top scored results as candidates"),
    limit: Optional[int] = Query(None, description="Override search limit"),
):
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    max_results = limit or settings.youtube_search_limit
    scored = search_youtube(track.artists, track.title, track.duration_ms, prefer_extended=prefer_extended, limit=max_results)

    # Optionally persist as SearchCandidate (avoid duplicates by external_id)
    out: List[SearchCandidateRead] = []
    if persist:
        existing_stmt = select(SearchCandidate.external_id).where(
            SearchCandidate.track_id == track.id,
            SearchCandidate.provider == SearchProvider.youtube,
        )
        existing = set((await session.execute(existing_stmt)).scalars().all())
        rank_cut = 10  # persist at most top 10 even if search limit larger
        for sr in scored[:rank_cut]:
            if sr.external_id in existing:
                continue
            sc = SearchCandidate(
                track_id=track.id,
                provider=SearchProvider.youtube,
                external_id=sr.external_id,
                url=sr.url,
                title=sr.title,
                channel=sr.channel,
                duration_sec=sr.duration_sec,
                score=sr.score,
            )
            session.add(sc)
        await session.flush()
        # Re-query all youtube candidates for this track sorted by score desc
        result = await session.execute(
            select(SearchCandidate).where(
                SearchCandidate.track_id == track.id,
                SearchCandidate.provider == SearchProvider.youtube,
            ).order_by(desc(SearchCandidate.score))
        )
        rows: List[SearchCandidate] = result.scalars().all()
        for c in rows:
            # Build pydantic object manually to add duration_delta_sec like candidates API does
            from ..v1.candidates import _attach_computed  # type: ignore
            out.append(_attach_computed(track.duration_ms, c))
    else:
        # Return transient scored list
        for sr in scored:
            out.append(
                SearchCandidateRead(
                    id=0,  # transient placeholder
                    track_id=track.id,
                    provider=SearchProvider.youtube,  # type: ignore[arg-type]
                    external_id=sr.external_id,
                    url=sr.url,
                    title=sr.title,
                    channel=sr.channel,
                    duration_sec=sr.duration_sec,
                    score=sr.score,
                    chosen=False,
                    created_at=track.created_at,
                    duration_delta_sec=duration_delta_sec(track.duration_ms, sr.duration_sec * 1000) if (track.duration_ms and sr.duration_sec) else None,  # type: ignore[arg-type]
                )
            )
    return out
