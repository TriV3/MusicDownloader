from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import SearchCandidate, Track  # type: ignore
    from ...schemas.models import SearchCandidateCreate, SearchCandidateRead  # type: ignore
    from ...utils.normalize import duration_delta_sec  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import SearchCandidate, Track  # type: ignore
    from schemas.models import SearchCandidateCreate, SearchCandidateRead  # type: ignore
    from utils.normalize import duration_delta_sec  # type: ignore

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _attach_computed(track_duration_ms: Optional[int], cand: SearchCandidate) -> SearchCandidateRead:
    # Build pydantic object manually to inject computed field
    base = SearchCandidateRead.model_validate(cand, from_attributes=True)
    if track_duration_ms is not None and cand.duration_sec is not None:
        delta = duration_delta_sec(track_duration_ms, cand.duration_sec * 1000)
    else:
        delta = None
    base.duration_delta_sec = delta
    return base


@router.get("/", response_model=List[SearchCandidateRead])
async def list_candidates(
    session: AsyncSession = Depends(get_session),
    track_id: Optional[int] = Query(None),
    sort: Optional[str] = Query(None, description="score (default desc) | duration_delta"),
    chosen_only: bool = Query(False),
):
    stmt = select(SearchCandidate)
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
    track_duration_ms = None
    if track_id is not None:
        track = await session.get(Track, track_id)
        track_duration_ms = track.duration_ms if track else None
    enriched = [_attach_computed(track_duration_ms, c) for c in rows]
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
    return _attach_computed(track.duration_ms, cand)


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
    return _attach_computed(track.duration_ms if track else None, cand)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int, session: AsyncSession = Depends(get_session)):
    cand = await session.get(SearchCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    await session.delete(cand)
    return {"deleted": True}
