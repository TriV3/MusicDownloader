from typing import List, Optional
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, desc, asc
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
    from ...utils.images import youtube_thumbnail_url  # type: ignore
    from ...db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from ...core.config import settings  # type: ignore
    import httpx  # type: ignore
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
    from utils.images import youtube_thumbnail_url  # type: ignore
    from db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from core.config import settings  # type: ignore
    import httpx  # type: ignore


router = APIRouter(prefix="/tracks", tags=["tracks"])

@router.get("/raw_min")
async def list_tracks_raw_min(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(5, ge=1, le=1000),
):
    stmt = select(Track).order_by(desc(Track.updated_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for t in rows:
        out.append({
            "id": t.id,
            "title": t.title,
            "artists": t.artists,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })
    return out


@router.get("/", response_model=List[TrackRead])
async def list_tracks(
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(None, description="Filter by title/artists contains (case-insensitive)"),
    playlist_id: Optional[int] = Query(None, description="Filter by playlist id and order by playlist position"),
    limit: int = Query(100, ge=1, le=1000),
):
    # Default ordering
    stmt = select(Track)
    order_cols = [desc(Track.updated_at)]

    # Filter by search query
    if q:
        from sqlalchemy import or_, func
        like = f"%{q.lower()}%"
        stmt = select(Track).where(
            or_(func.lower(Track.title).like(like), func.lower(Track.artists).like(like))
        )

    # Filter by playlist: join PlaylistTrack to constrain and order by position
    if playlist_id is not None:
        stmt = stmt.join(PlaylistTrack, PlaylistTrack.track_id == Track.id).where(
            PlaylistTrack.playlist_id == playlist_id
        )
        order_cols = [asc(PlaylistTrack.position.nullslast()), desc(Track.updated_at)]

    stmt = stmt.order_by(*order_cols).limit(limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    try:
        import logging
        logging.getLogger("tracks").info("list_tracks returned %s rows (limit=%s, playlist_id=%s)", len(rows), limit, playlist_id)
        if rows:
            logging.getLogger("tracks").debug("first track id=%s title=%s", rows[0].id, rows[0].title)
    except Exception:
        pass
    return rows


# Accept both with and without trailing slash
@router.get("", response_model=List[TrackRead])
async def list_tracks_no_slash(
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(None, description="Filter by title/artists contains (case-insensitive)"),
    playlist_id: Optional[int] = Query(None, description="Filter by playlist id and order by playlist position"),
    limit: int = Query(100, ge=1, le=1000),
):
    return await list_tracks(session=session, q=q, playlist_id=playlist_id, limit=limit)


@router.get("/with_playlist_info", response_model=List[dict])
async def list_tracks_with_playlist_info(
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(None, description="Filter by title/artists contains (case-insensitive)"),
    playlist_id: Optional[int] = Query(None, description="Filter by playlist id"),
    track_id: Optional[int] = Query(None, description="Filter by specific track id"),
    sort_by: Optional[str] = Query("updated_at", description="Sort by: updated_at, release_date, playlist_added_at"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Return tracks enriched with playlist information for enhanced sorting and display."""
    from sqlalchemy import func, case
    from ...db.models.models import Playlist, Download, DownloadStatus  # type: ignore
    
    # Base query with playlist join and download info
    stmt = (
        select(
            Track,
            PlaylistTrack.added_at.label("playlist_added_at"),
            PlaylistTrack.position.label("playlist_position"),
            Playlist.name.label("playlist_name"),
            Download.finished_at.label("downloaded_at")
        )
        .outerjoin(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .outerjoin(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .outerjoin(Download, (Download.track_id == Track.id) & (Download.status == DownloadStatus.done))
    )

    # Filter by search query
    if q:
        from sqlalchemy import or_
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Track.title).like(like), func.lower(Track.artists).like(like))
        )

    # Filter by specific playlist
    if playlist_id is not None:
        stmt = stmt.where(PlaylistTrack.playlist_id == playlist_id)

    # Filter by specific track ID
    if track_id is not None:
        stmt = stmt.where(Track.id == track_id)

    # Determine sort column
    sort_column = desc(Track.updated_at)  # default
    if sort_by == "release_date":
        if sort_order == "asc":
            sort_column = asc(Track.release_date.nullslast())
        else:
            sort_column = desc(Track.release_date.nullslast())
    elif sort_by == "playlist_added_at":
        if sort_order == "asc":
            sort_column = asc(PlaylistTrack.added_at.nullslast())
        else:
            sort_column = desc(PlaylistTrack.added_at.nullslast())
    elif sort_by == "updated_at":
        if sort_order == "asc":
            sort_column = asc(Track.updated_at)
        else:
            sort_column = desc(Track.updated_at)

    stmt = stmt.order_by(sort_column).limit(limit)
    result = await session.execute(stmt)
    rows = result.all()

    # Transform results to include playlist info
    tracks_with_playlist = []
    tracks_dict = {}
    
    for row in rows:
        track = row[0]
        track_id = track.id
        
        # If track not yet in dict, create base track object
        if track_id not in tracks_dict:
            tracks_dict[track_id] = {
                "id": track.id,
                "title": track.title,
                "artists": track.artists,
                "album": track.album,
                "duration_ms": track.duration_ms,
                "isrc": track.isrc,
                "year": track.year,
                "explicit": track.explicit,
                "cover_url": track.cover_url,
                "normalized_title": track.normalized_title,
                "normalized_artists": track.normalized_artists,
                "genre": track.genre,
                "bpm": track.bpm,
                "release_date": track.release_date.isoformat() if track.release_date else None,  # Date de release de la track sur Spotify
                "downloaded_at": row.downloaded_at.isoformat() if row.downloaded_at else None,  # Date de téléchargement
                "playlists": []
            }
        
        # Add playlist info if exists
        if row.playlist_added_at and row.playlist_name:
            playlist_info = {
                "playlist_name": row.playlist_name,
                "playlist_added_at": row.playlist_added_at.isoformat(),  # When added to playlist
                "position": row.playlist_position
            }
            tracks_dict[track_id]["playlists"].append(playlist_info)
    
    # Convert dict to list
    tracks_with_playlist = list(tracks_dict.values())

    return tracks_with_playlist


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


@router.get("/ready_for_download", response_model=List[TrackRead])
async def ready_for_download(
    session: AsyncSession = Depends(get_session),
    include_downloaded: bool = Query(False, description="Include tracks that already have a successful download"),
):
    """Return tracks that have a chosen candidate. By default excludes tracks that already have a done download."""
    # Tracks with chosen candidate
    cand_stmt = select(SearchCandidate.track_id).where(SearchCandidate.chosen.is_(True))
    cand_ids = set((await session.execute(cand_stmt)).scalars().all())
    if not cand_ids:
        return []
    # Optionally exclude tracks that already have a library file on disk
    ready_ids: list[int]
    if include_downloaded:
        ready_ids = list(cand_ids)
    else:
        from ...db.models.models import LibraryFile  # type: ignore
        lf_stmt = select(LibraryFile.track_id)
        lf_ids = set((await session.execute(lf_stmt)).scalars().all())
        ready_ids = list(cand_ids - lf_ids)
    if not ready_ids:
        return []
    q = select(Track).where(Track.id.in_(ready_ids)).order_by(desc(Track.updated_at))
    rows = (await session.execute(q)).scalars().all()
    return rows


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


@router.get("/{track_id}/identities")
async def get_track_identities(track_id: int, session: AsyncSession = Depends(get_session)):
    # Verify track exists
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    # Get all identities for this track
    stmt = select(TrackIdentity).where(TrackIdentity.track_id == track_id)
    result = await session.execute(stmt)
    identities = result.scalars().all()
    
    return [
        {
            "id": identity.id,
            "provider": identity.provider.value,
            "provider_track_id": identity.provider_track_id,
            "provider_url": identity.provider_url,
            "fingerprint": identity.fingerprint,
            "created_at": identity.created_at.isoformat(),
            "updated_at": identity.updated_at.isoformat(),
        }
        for identity in identities
    ]


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
        # If track has no cover yet, set it from the top scored candidate's thumbnail
        if not track.cover_url and scored:
            thumb = youtube_thumbnail_url(scored[0].external_id) or youtube_thumbnail_url(scored[0].url)
            if thumb:
                track.cover_url = thumb
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
            out.append(_attach_computed(track, c))
    else:
        # Return transient scored list
        from ...utils.youtube_search import get_score_components  # type: ignore
        for sr in scored:
            comps = get_score_components(
                query_artists=track.artists,
                query_title=track.title,
                track_duration_ms=track.duration_ms,
                result_duration_sec=sr.duration_sec,
                result_title=sr.title,
                result_channel=sr.channel,
            )
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
                    score_breakdown=SearchCandidateRead.ScoreBreakdown(
                        artist=comps[0],
                        title=comps[1],
                        duration=comps[3],
                        extended=comps[2],
                        total=comps[5],
                    ),
                )
            )
    return out


@router.post("/{track_id}/cover/refresh", response_model=TrackRead)
async def refresh_track_cover(track_id: int, session: AsyncSession = Depends(get_session)):
    """Refresh track cover from available identities.

    Strategy:
    - If Spotify identity exists, fetch track details and use album image (first image url).
    - Else if chosen YouTube candidate exists, set thumbnail.
    - Else leave unchanged.
    """
    track = await session.get(Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    # Try Spotify identity
    result = await session.execute(
        select(TrackIdentity).where(
            TrackIdentity.track_id == track_id,
            TrackIdentity.provider == SourceProvider.spotify,
        )
    )
    sp_identity: Optional[TrackIdentity] = result.scalars().first()
    new_cover: Optional[str] = None
    if sp_identity and sp_identity.provider_track_id:
        # Use Spotify Web API to fetch track -> album images
        # Expect a global OAuth token stored in oauth_tokens; in absence, skip.
        try:
            from ..v1.oauth_spotify import _get_env  # type: ignore
            from ..v1.oauth_spotify import SPOTIFY_TOKEN_URL  # type: ignore
        except Exception:  # pragma: no cover
            _get_env = None  # type: ignore
        # We don't implement token exchange here; assume a valid token exists in DB or env for simplicity
        access_token = None
        try:
            # Prefer DB token
            from ...db.models.models import OAuthToken  # type: ignore
            tokres = await session.execute(select(OAuthToken).order_by(desc(OAuthToken.updated_at)))
            tok = tokres.scalars().first()
            if tok:
                access_token = tok.access_token
        except Exception:
            access_token = None
        if not access_token:
            # Optional: allow direct env var for quick dev tests
            import os
            access_token = os.environ.get("SPOTIFY_ACCESS_TOKEN")
        if access_token:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://api.spotify.com/v1/tracks/{sp_identity.provider_track_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    images = (((data or {}).get("album") or {}).get("images") or [])
                    if images:
                        new_cover = images[0].get("url")
            except Exception:
                pass

    # Fallback to chosen YouTube candidate
    if not new_cover:
        result2 = await session.execute(
            select(SearchCandidate)
            .where(SearchCandidate.track_id == track_id, SearchCandidate.chosen.is_(True))
            .order_by(desc(SearchCandidate.score))
        )
        chosen = result2.scalars().first()
        if chosen and chosen.provider == SearchProvider.youtube:
            new_cover = youtube_thumbnail_url(chosen.external_id) or youtube_thumbnail_url(chosen.url)

    if new_cover:
        track.cover_url = new_cover
        await session.flush()
    return track
