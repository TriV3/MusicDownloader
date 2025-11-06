from typing import List, Optional
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import os

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import SearchCandidate, Track, SearchProvider  # type: ignore
    from ...schemas.models import SearchCandidateCreate, SearchCandidateRead  # type: ignore
    from ...utils.normalize import duration_delta_sec, normalize_track  # type: ignore
    from ...utils.images import youtube_thumbnail_url  # type: ignore
    from ...utils.youtube_search import get_score_components  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import SearchCandidate, Track, SearchProvider  # type: ignore
    from schemas.models import SearchCandidateCreate, SearchCandidateRead  # type: ignore
    from utils.normalize import duration_delta_sec, normalize_track  # type: ignore
    from utils.images import youtube_thumbnail_url  # type: ignore
    from utils.youtube_search import get_score_components  # type: ignore

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _attach_computed(track: Optional[Track], cand: SearchCandidate) -> SearchCandidateRead:
    # Build pydantic object manually to inject computed field
    base = SearchCandidateRead.model_validate(cand, from_attributes=True)
    
    # Include track information
    if track:
        from ...schemas.models import TrackRead
        base.track = TrackRead.model_validate(track, from_attributes=True)
    elif hasattr(cand, 'track') and cand.track:
        from ...schemas.models import TrackRead
        base.track = TrackRead.model_validate(cand.track, from_attributes=True)
    
    if (track and track.duration_ms is not None) and (cand.duration_sec is not None):
        delta = duration_delta_sec(track.duration_ms, cand.duration_sec * 1000)
    elif base.track and base.track.duration_ms is not None and cand.duration_sec is not None:
        delta = duration_delta_sec(base.track.duration_ms, cand.duration_sec * 1000)
    else:
        delta = None
    base.duration_delta_sec = delta
    
    # Use track info from base.track if track parameter is None
    track_for_scoring = track or base.track
    
    # Attach score breakdown when provider is youtube and track context is available
    if cand.provider == SearchProvider.youtube and track_for_scoring is not None:
        comps = get_score_components(
            query_artists=track_for_scoring.artists,
            query_title=track_for_scoring.title,
            track_duration_ms=track_for_scoring.duration_ms,
            result_duration_sec=cand.duration_sec,
            result_title=cand.title,
            result_channel=cand.channel,
        )
        # comps = (artist, title, extended, duration, penalty, total)
        # All values are from RankingService
        base.score_breakdown = SearchCandidateRead.ScoreBreakdown(
            artist=comps[0],
            title=comps[1],
            duration=comps[3],
            extended=comps[2],
            total=comps[5],
        )
    return base


@router.get("/enriched", response_model=List[SearchCandidateRead])
async def list_candidates_enriched(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    sort: Optional[str] = Query(None, description="score (default desc) | duration_delta"),
    chosen_only: bool = Query(False),
    min_score: Optional[float] = Query(None, description="Minimum score threshold to include non-chosen candidates"),
    drop_negative: Optional[bool] = Query(None, description="When true, exclude candidates with negative score (non-chosen)"),
):
    """
    Get candidates with enriched track and playlist information
    """
    from ...db.models.models import PlaylistTrack, Playlist
    from sqlalchemy.orm import selectinload, joinedload
    
    # Build query with all necessary joins and eager loading
    stmt = (
        select(SearchCandidate)
        .options(
            selectinload(SearchCandidate.track).selectinload(Track.playlist_entries).joinedload(PlaylistTrack.playlist)
        )
    )
    
    conds = []
    if track_id is not None:
        conds.append(SearchCandidate.track_id == track_id)
    if chosen_only:
        conds.append(SearchCandidate.chosen.is_(True))
    if conds:
        from sqlalchemy import and_ as _and
        stmt = stmt.where(_and(*conds))
    if sort == "score" or sort is None:
        stmt = stmt.order_by(desc(SearchCandidate.score))
    elif sort == "duration_delta":
        # We'll sort in python after computing delta since it depends on track duration
        pass
    
    result = await session.execute(stmt)
    rows = result.scalars().all()
    
    # Convert to enriched format
    enriched = []
    for cand in rows:
        # Build enriched candidate with playlist information
        track_data = None
        if cand.track:
            from ...schemas.models import TrackRead
            track_data = TrackRead.model_validate(cand.track, from_attributes=True)
            
            # Add playlist information
            if cand.track.playlist_entries:
                playlist_infos = []
                for pt in cand.track.playlist_entries:
                    playlist_info = TrackRead.PlaylistInfo(
                        playlist_id=pt.playlist_id,
                        playlist_name=pt.playlist.name if pt.playlist else f"Playlist {pt.playlist_id}",
                        added_at=pt.added_at,
                        position=pt.position
                    )
                    playlist_infos.append(playlist_info)
                track_data.playlists = playlist_infos
        
        enriched_cand = _attach_computed(cand.track, cand)
        enriched_cand.track = track_data
        enriched.append(enriched_cand)
    
    # Apply server-side filtering: drop negative scores by default and honor optional min score.
    def _env_min_score() -> Optional[float]:
        try:
            v = os.environ.get("YOUTUBE_SEARCH_MIN_SCORE")
            if not v:
                return None
            return float(v)
        except Exception:
            return None
    def _env_drop_negative() -> bool:
        return os.environ.get("YOUTUBE_SEARCH_DROP_NEGATIVE", "1") != "0"
    # Prefer explicit query params when provided, else fall back to env defaults
    effective_min_score = min_score if (min_score is not None) else _env_min_score()
    effective_drop_negative = drop_negative if (drop_negative is not None) else _env_drop_negative()
    # Keep chosen candidates regardless of thresholds; filter the rest by score
    filtered = []
    for item in enriched:
        if item.chosen:
            filtered.append(item)
            continue
        # Use the same metric the UI displays: score_breakdown.total when present, else raw score
        display_score: Optional[float] = None
        try:
            if getattr(item, "score_breakdown", None) is not None:
                display_score = getattr(item.score_breakdown, "total", None)  # type: ignore[attr-defined]
        except Exception:
            display_score = None
        if display_score is None:
            display_score = item.score
        if effective_drop_negative and (display_score is not None) and display_score < 0:
            continue
        if (effective_min_score is not None) and (display_score is not None) and display_score < effective_min_score:
            continue
        filtered.append(item)
    enriched = filtered
    if sort == "duration_delta":
        enriched.sort(key=lambda c: (c.duration_delta_sec is None, c.duration_delta_sec))
    return enriched


@router.get("/", response_model=List[SearchCandidateRead])
async def list_candidates(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    sort: Optional[str] = Query(None, description="score (default desc) | duration_delta"),
    chosen_only: bool = Query(False),
    min_score: Optional[float] = Query(None, description="Minimum score threshold to include non-chosen candidates"),
    drop_negative: Optional[bool] = Query(None, description="When true, exclude candidates with negative score (non-chosen)"),
):
    from ...db.models.models import PlaylistTrack, Playlist
    from sqlalchemy.orm import selectinload
    
    # Join with Track to get track information including playlist data
    stmt = select(SearchCandidate).options(selectinload(SearchCandidate.track))
    conds = []
    if track_id is not None:
        conds.append(SearchCandidate.track_id == track_id)
    if chosen_only:
        conds.append(SearchCandidate.chosen.is_(True))
    if conds:
        from sqlalchemy import and_ as _and
        stmt = stmt.where(_and(*conds))
    if sort == "score" or sort is None:
        stmt = stmt.order_by(desc(SearchCandidate.score))
    elif sort == "duration_delta":
        # We'll sort in python after computing delta since it depends on track duration
        pass
    result = await session.execute(stmt)
    rows = result.scalars().all()
    track_obj = None
    if track_id is not None:
        track_obj = await session.get(Track, track_id)
    # Compute breakdowns (RankingService handles all scoring logic)
    enriched = [_attach_computed(track_obj, c) for c in rows]
    # Apply server-side filtering: drop negative scores by default and honor optional min score.
    def _env_min_score() -> Optional[float]:
        try:
            v = os.environ.get("YOUTUBE_SEARCH_MIN_SCORE")
            if not v:
                return None
            return float(v)
        except Exception:
            return None
    def _env_drop_negative() -> bool:
        return os.environ.get("YOUTUBE_SEARCH_DROP_NEGATIVE", "1") != "0"
    # Prefer explicit query params when provided, else fall back to env defaults
    effective_min_score = min_score if (min_score is not None) else _env_min_score()
    effective_drop_negative = drop_negative if (drop_negative is not None) else _env_drop_negative()
    # Keep chosen candidates regardless of thresholds; filter the rest by score
    filtered = []
    for item in enriched:
        if item.chosen:
            filtered.append(item)
            continue
        # Use the same metric the UI displays: score_breakdown.total when present, else raw score
        display_score: Optional[float] = None
        try:
            if getattr(item, "score_breakdown", None) is not None:
                display_score = getattr(item.score_breakdown, "total", None)  # type: ignore[attr-defined]
        except Exception:
            display_score = None
        if display_score is None:
            display_score = item.score
        if effective_drop_negative and (display_score is not None) and display_score < 0:
            continue
        if (effective_min_score is not None) and (display_score is not None) and display_score < effective_min_score:
            continue
        filtered.append(item)
    enriched = filtered
    if sort == "duration_delta":
        enriched.sort(key=lambda c: (c.duration_delta_sec is None, c.duration_delta_sec))
    return enriched


@router.post("/", response_model=SearchCandidateRead)
async def create_candidate(payload: SearchCandidateCreate, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, payload.track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    cand = SearchCandidate(**payload.model_dump())
    session.add(cand)
    await session.flush()
    return _attach_computed(track, cand)


@router.post("/{candidate_id}/choose", response_model=SearchCandidateRead)
async def choose_candidate(candidate_id: int, session: AsyncSession = Depends(get_session)):
    cand = await session.get(SearchCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    # Clear existing chosen for this track
    stmt = select(SearchCandidate).where(SearchCandidate.track_id == cand.track_id)
    result = await session.execute(stmt)
    for other in result.scalars():
        other.chosen = (other.id == cand.id)
    await session.flush()
    track = await session.get(Track, cand.track_id)
    # If choosing a YouTube candidate and track cover is missing, set thumbnail
    if track and not track.cover_url and cand.provider == SearchProvider.youtube:
        thumb = youtube_thumbnail_url(cand.external_id) or youtube_thumbnail_url(cand.url)
        if thumb:
            track.cover_url = thumb
    return _attach_computed(track, cand)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int, session: AsyncSession = Depends(get_session)):
    cand = await session.get(SearchCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    await session.delete(cand)
    return {"deleted": True}
