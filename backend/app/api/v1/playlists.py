from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, delete, func, distinct, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Playlist, SourceProvider, SourceAccount, OAuthToken, Track, TrackIdentity, PlaylistTrack  # type: ignore
    from ...schemas.models import PlaylistCreate, PlaylistRead, TrackRead  # type: ignore
    from ...core.config import settings  # type: ignore
    from ...utils.normalize import normalize_track  # type: ignore
    from ...db.models.models import LibraryFile  # type: ignore
    from ...db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from ...db.models.models import DownloadProvider  # type: ignore
    from ...utils.youtube_search import search_youtube  # type: ignore
    from ...api.v1.downloads import enqueue_download  # type: ignore
    from ...utils.images import youtube_thumbnail_url  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Playlist, SourceProvider, SourceAccount, OAuthToken, Track, TrackIdentity, PlaylistTrack  # type: ignore
    from schemas.models import PlaylistCreate, PlaylistRead, TrackRead  # type: ignore
    from core.config import settings  # type: ignore
    from utils.normalize import normalize_track  # type: ignore
    from db.models.models import LibraryFile  # type: ignore
    from db.models.models import SearchCandidate, SearchProvider  # type: ignore
    from db.models.models import DownloadProvider  # type: ignore
    from utils.youtube_search import search_youtube  # type: ignore
    from api.v1.downloads import enqueue_download  # type: ignore
    from utils.images import youtube_thumbnail_url  # type: ignore

import os
import httpx
import time


router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("/", response_model=List[PlaylistRead])
async def list_playlists(
    provider: Optional[SourceProvider] = Query(None),
    account_id: Optional[int] = Query(None),
    selected: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Playlist)
    conds = []
    if provider is not None:
        conds.append(Playlist.provider == provider)
    if account_id is not None:
        conds.append(Playlist.source_account_id == account_id)
    if selected is not None:
        conds.append(Playlist.selected == selected)
    if conds:
        stmt = stmt.where(and_(*conds))
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=PlaylistRead)
async def create_playlist(payload: PlaylistCreate, session: AsyncSession = Depends(get_session)):
    playlist = Playlist(**payload.model_dump())
    session.add(playlist)
    await session.flush()
    return playlist


def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env {name}")
    return value


@router.get("/stats")
async def playlists_stats(
    include_other: bool = Query(True, description="Include 'other' category for manually added tracks without any playlist"),
    selected_only: bool = Query(True, description="When true, only include playlists with selected=true"),
    provider: Optional[SourceProvider] = Query(None, description="Filter by provider (e.g., spotify)"),
    account_id: Optional[int] = Query(None, description="Filter by source account id"),
    session: AsyncSession = Depends(get_session),
):
    # Per-playlist stats: total distinct tracks and distinct downloaded tracks (has a LibraryFile.exists)
    stmt = (
        select(
            Playlist.id.label("playlist_id"),
            Playlist.name.label("name"),
            Playlist.provider.label("provider"),
            func.count(distinct(PlaylistTrack.track_id)).label("total_tracks"),
            func.count(distinct(case((LibraryFile.exists == True, PlaylistTrack.track_id)))).label("downloaded_tracks"),  # noqa: E712
        )
        .select_from(Playlist)
        .join(PlaylistTrack, PlaylistTrack.playlist_id == Playlist.id, isouter=True)
        .join(
            LibraryFile,
            (LibraryFile.track_id == PlaylistTrack.track_id) & (LibraryFile.exists == True),  # noqa: E712
            isouter=True,
        )
    )

    conds = []
    if selected_only:
        conds.append(Playlist.selected == True)  # noqa: E712
    if provider is not None:
        conds.append(Playlist.provider == provider)
    if account_id is not None:
        conds.append(Playlist.source_account_id == account_id)
    if conds:
        stmt = stmt.where(and_(*conds))

    stmt = stmt.group_by(Playlist.id).order_by(Playlist.name.asc())
    res = await session.execute(stmt)
    items = []
    # Preload counts of searches with zero results per track
    try:
        from ...db.models.models import SearchAttempt as _SA  # type: ignore
    except Exception:  # pragma: no cover
        from db.models.models import SearchAttempt as _SA  # type: ignore
    nf_stmt = (
        select(PlaylistTrack.playlist_id, func.count(_SA.id))
        .select_from(PlaylistTrack)
        .join(_SA, _SA.track_id == PlaylistTrack.track_id)
        .where(_SA.results_count == 0)
        .group_by(PlaylistTrack.playlist_id)
    )
    nf_map: Dict[int, int] = {pid: cnt for pid, cnt in (await session.execute(nf_stmt)).all()}

    for row in res.all():
        row = row._asdict()
        total = int(row.get("total_tracks") or 0)
        downloaded = int(row.get("downloaded_tracks") or 0)
        pid = row.get("playlist_id")
        items.append({
            "playlist_id": pid,
            "name": row.get("name"),
            "provider": (row.get("provider") or "").value if hasattr(row.get("provider"), "value") else row.get("provider"),
            "total_tracks": total,
            "downloaded_tracks": downloaded,
            "not_downloaded_tracks": max(0, total - downloaded),
            "searched_not_found": int(nf_map.get(pid, 0)) if pid is not None else 0,
        })

    if include_other:
        # Tracks with a MANUAL identity and not present in any playlist
        other_stmt = (
            select(
                func.count(distinct(Track.id)).label("total_tracks"),
                func.count(distinct(case((LibraryFile.exists == True, Track.id)))).label("downloaded_tracks"),  # noqa: E712
            )
            .select_from(Track)
            .join(TrackIdentity, (TrackIdentity.track_id == Track.id) & (TrackIdentity.provider == SourceProvider.manual))
            .join(PlaylistTrack, PlaylistTrack.track_id == Track.id, isouter=True)
            .join(LibraryFile, (LibraryFile.track_id == Track.id) & (LibraryFile.exists == True), isouter=True)  # noqa: E712
            .where(PlaylistTrack.id.is_(None))
        )
        other_res = await session.execute(other_stmt)
        total_o, downloaded_o = other_res.first() or (0, 0)
        total_o = int(total_o or 0)
        downloaded_o = int(downloaded_o or 0)
        # Only include the synthetic 'Other' bucket when it has at least one track
        if total_o > 0:
            items.append({
                "playlist_id": None,
                "name": "Other",
                "provider": "other",
                "total_tracks": total_o,
                "downloaded_tracks": downloaded_o,
                "not_downloaded_tracks": max(0, total_o - downloaded_o),
                "searched_not_found": 0,
            })

    return items


@router.get("/{playlist_id}", response_model=PlaylistRead)
async def get_playlist(playlist_id: int, session: AsyncSession = Depends(get_session)):
    """Retrieve a playlist by its internal id.

    Placed after static routes (e.g., /stats) to avoid capturing those paths
    as a dynamic parameter and causing 422 errors.
    """
    playlist = await session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


@router.post("/{playlist_id}/auto_download")
async def auto_download_playlist(
    playlist_id: int,
    session: AsyncSession = Depends(get_session),
    prefer_extended: bool = Query(False, description="Prefer Extended/Club/Original Mix when searching"),
    dry_run: bool = Query(False, description="If true, do not create candidates or downloads; return what would be enqueued"),
):
    """Search best YouTube candidate per track in playlist and enqueue downloads.

    Behavior:
    - Skips tracks that already have a LibraryFile.exists on disk (duplicate prevention).
    - If a chosen candidate exists, enqueues download for it.
    - Otherwise, performs YouTube search, persists the top scored result as a candidate (chosen), and enqueues it.
    - Honors server-side filtering (min score, drop negatives) applied in search_youtube.
    - Returns a summary of actions.
    """
    pl = await session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")

    # Fetch tracks in playlist order
    result = await session.execute(
        select(PlaylistTrack, Track)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position.asc())
    )
    rows = result.all()

    total = len(rows)
    skipped_already = 0
    enqueued = 0
    candidates_created = 0
    not_found = 0
    chosen_used = 0

    for pt, tr in rows:
        # Skip if a library file exists (best-effort check)
        has_file = False
        try:
            lf_q = select(LibraryFile).where(LibraryFile.track_id == tr.id, LibraryFile.exists == True)  # noqa: E712
            lf = (await session.execute(lf_q)).scalars().first()
            if lf and lf.filepath:
                import os as _os
                if _os.path.exists(lf.filepath):
                    has_file = True
        except Exception:
            has_file = False
        if has_file:
            skipped_already += 1
            continue

        # Use chosen candidate if present
        chosen = (await session.execute(
            select(SearchCandidate)
            .where(SearchCandidate.track_id == tr.id, SearchCandidate.chosen.is_(True))
            .order_by(desc(SearchCandidate.score))
        )).scalars().first()

        cand_id: Optional[int] = None
        if chosen is not None:
            cand_id = chosen.id
            chosen_used += 1
        else:
            # Perform YouTube search and pick top result
            scored = search_youtube(tr.artists, tr.title, tr.duration_ms, prefer_extended=prefer_extended)
            top = scored[0] if scored else None
            # Record search attempt result count
            try:
                from ...db.models.models import SearchAttempt, SearchProvider as _SP  # type: ignore
            except Exception:  # pragma: no cover
                from db.models.models import SearchAttempt, SearchProvider as _SP  # type: ignore
            try:
                att = SearchAttempt(
                    track_id=tr.id,
                    provider=_SP.youtube,
                    results_count=len(scored or []),
                    prefer_extended=prefer_extended,
                )
                session.add(att)
                await session.flush()
            except Exception:
                pass
            if not top:
                not_found += 1
                continue
            if not dry_run:
                # Persist as candidate (upsert) and mark chosen
                # Clear any previous chosen flags just in case
                prev = (await session.execute(select(SearchCandidate).where(SearchCandidate.track_id == tr.id))).scalars().all()
                for c in prev:
                    c.chosen = False
                existing = (await session.execute(
                    select(SearchCandidate).where(
                        SearchCandidate.track_id == tr.id,
                        SearchCandidate.provider == SearchProvider.youtube,
                        SearchCandidate.external_id == top.external_id,
                    )
                )).scalars().first()
                if existing:
                    existing.url = top.url
                    existing.title = top.title
                    existing.channel = top.channel
                    existing.duration_sec = top.duration_sec
                    existing.score = top.score
                    existing.chosen = True
                    sc = existing
                else:
                    sc = SearchCandidate(
                        track_id=tr.id,
                        provider=SearchProvider.youtube,
                        external_id=top.external_id,
                        url=top.url,
                        title=top.title,
                        channel=top.channel,
                        duration_sec=top.duration_sec,
                        score=top.score,
                        chosen=True,
                    )
                    session.add(sc)
                    candidates_created += 1
                await session.flush()
                cand_id = sc.id
                # Set cover if missing from YouTube thumbnail
                if not tr.cover_url:
                    thumb = youtube_thumbnail_url(top.external_id) or youtube_thumbnail_url(top.url)
                    if thumb:
                        tr.cover_url = thumb

        if dry_run:
            # Skip actual enqueue
            continue

        # Enqueue download (reuses duplicate prevention inside)
        try:
            dl = await enqueue_download(
                track_id=tr.id,
                candidate_id=cand_id,
                provider=DownloadProvider.yt_dlp,
                force=False,
                session=session,
            )
            # Count only when queued or marked already/done
            if getattr(dl, "status", None) is not None:
                enqueued += 1
        except HTTPException as e:
            # Skip on errors like 404/validation; continue with next track
            continue

    return {
        "playlist_id": playlist_id,
        "total_tracks": total,
        "skipped_already": skipped_already,
        "chosen_used": chosen_used,
        "candidates_created": candidates_created,
        "enqueued": enqueued,
        "not_found": not_found,
        "dry_run": dry_run,
    }


async def _get_valid_token(session: AsyncSession, account_id: int) -> str:
    # naive token retrieval; Step 0.3 already stores tokens
    result = await session.execute(select(OAuthToken).where(OAuthToken.source_account_id == account_id))
    tok = result.scalars().first()
    if not tok:
        raise HTTPException(status_code=404, detail="No OAuth token for this account")
    # Skipping refresh path for brevity; tests can mock stable token
    return tok.access_token


@router.get("/spotify/discover", response_model=List[PlaylistRead])
async def spotify_discover_playlists(
    account_id: int = Query(..., description="Spotify SourceAccount id"),
    persist: bool = Query(False, description="Persist/Upsert discovered playlists"),
    session: AsyncSession = Depends(get_session),
):
    account = await session.get(SourceAccount, account_id)
    if not account or account.type != SourceProvider.spotify:
        raise HTTPException(status_code=404, detail="Spotify account not found")

    access_token = await _get_valid_token(session, account_id)
    items: List[dict] = []
    async with httpx.AsyncClient(timeout=20) as client:
        url = "https://api.spotify.com/v1/me/playlists?limit=50"
        while url:
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Spotify API error: {resp.text}")
            data = resp.json()
            items.extend(data.get("items", []))
            url = data.get("next")

    discovered: List[Playlist] = []
    for it in items:
        pl_id = it.get("id")
        name = it.get("name")
        desc = it.get("description")
        owner = (it.get("owner") or {}).get("display_name") or (it.get("owner") or {}).get("id")
        snapshot_id = it.get("snapshot_id")
        # Upsert if persist
        if persist:
            result = await session.execute(
                select(Playlist).where(
                    Playlist.provider == SourceProvider.spotify,
                    Playlist.provider_playlist_id == pl_id,
                )
            )
            existing = result.scalars().first()
            if existing:
                existing.name = name
                existing.description = desc
                existing.owner = owner
                existing.snapshot = snapshot_id
                if existing.source_account_id is None:
                    existing.source_account_id = account_id
                discovered.append(existing)
            else:
                p = Playlist(
                    provider=SourceProvider.spotify,
                    name=name,
                    description=desc,
                    owner=owner,
                    snapshot=snapshot_id,
                    source_account_id=account_id,
                    provider_playlist_id=pl_id,
                )
                session.add(p)
                await session.flush()
                discovered.append(p)
        else:
            p = Playlist(
                provider=SourceProvider.spotify,
                name=name,
                description=desc,
                owner=owner,
                snapshot=snapshot_id,
                source_account_id=account_id,
                provider_playlist_id=pl_id,
            )
            discovered.append(p)

    return discovered


@router.post("/spotify/select", response_model=List[PlaylistRead])
async def spotify_select_playlists(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    account_id = int(body.get("account_id"))
    playlist_ids = list(body.get("playlist_ids") or [])
    # Ensure rows exist; if not, create minimal ones
    selected_rows: List[Playlist] = []
    for pid in playlist_ids:
        result = await session.execute(
            select(Playlist).where(
                Playlist.provider == SourceProvider.spotify,
                Playlist.provider_playlist_id == pid,
            )
        )
        pl = result.scalars().first()
        if not pl:
            pl = Playlist(
                provider=SourceProvider.spotify,
                name=pid,
                source_account_id=account_id,
                provider_playlist_id=pid,
                selected=True,
            )
            session.add(pl)
            await session.flush()
        pl.selected = True
        if pl.source_account_id is None:
            pl.source_account_id = account_id
        selected_rows.append(pl)

    # Optionally unselect others of same account
    result = await session.execute(
        select(Playlist).where(
            Playlist.provider == SourceProvider.spotify,
            Playlist.source_account_id == account_id,
        )
    )
    for row in result.scalars().all():
        if row.provider_playlist_id not in playlist_ids:
            row.selected = False

    return selected_rows


@router.post("/spotify/sync")
async def spotify_sync_playlists(
    account_id: int = Query(..., description="Spotify SourceAccount id"),
    body: Optional[Dict[str, Any]] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Sync selected Spotify playlists (or a provided subset) into local Tracks and PlaylistTrack mappings.

    Incremental behaviour (Step 3.3):
    - Each playlist's current Spotify `snapshot_id` is fetched first.
    - If the stored `Playlist.snapshot` matches the remote snapshot, the playlist is skipped entirely.
    - When the snapshot differs (or none stored), a full fetch of tracks occurs and:
        * New tracks + identities are created.
        * Existing tracks are minimally updated & re-normalized if core fields changed.
        * PlaylistTrack links are created/updated (position / added_at).
        * Links for tracks no longer present in the remote playlist are deleted (removals).
        * The playlist's stored snapshot is updated to the new snapshot id.

    Body (optional): { "playlist_ids": ["spotify_playlist_id", ...] }

    Returns a summary including created/updated/linked/removed counts and skipped playlists.
    """
    account = await session.get(SourceAccount, account_id)
    if not account or account.type != SourceProvider.spotify:
        raise HTTPException(status_code=404, detail="Spotify account not found")

    # Determine target playlists
    explicit_ids = set((body or {}).get("playlist_ids") or [])
    target_playlists: List[Playlist] = []
    if explicit_ids:
        result = await session.execute(
            select(Playlist).where(
                Playlist.provider == SourceProvider.spotify,
                Playlist.provider_playlist_id.in_(list(explicit_ids)),
            )
        )
        target_playlists = result.scalars().all()
        # Ensure all requested ids exist minimally
        existing_ids = {p.provider_playlist_id for p in target_playlists}
        for pid in explicit_ids:
            if pid not in existing_ids:
                p = Playlist(
                    provider=SourceProvider.spotify,
                    name=pid,
                    source_account_id=account_id,
                    provider_playlist_id=pid,
                    selected=True,
                )
                session.add(p)
                await session.flush()
                target_playlists.append(p)
    else:
        result = await session.execute(
            select(Playlist).where(
                Playlist.provider == SourceProvider.spotify,
                Playlist.source_account_id == account_id,
                Playlist.selected == True,  # noqa: E712
            )
        )
        target_playlists = result.scalars().all()

    if not target_playlists:
        return {"playlists": [], "total_tracks_created": 0, "total_tracks_updated": 0, "total_links_created": 0}

    access_token = await _get_valid_token(session, account_id)

    async def fetch_playlist_snapshot(pl_id: str) -> Optional[str]:
        """Fetch only the snapshot id for a playlist (cheap metadata call)."""
        async with httpx.AsyncClient(timeout=15) as client:
            url = f"https://api.spotify.com/v1/playlists/{pl_id}?fields=snapshot_id"
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Spotify API error: {resp.text}")
            data = resp.json() or {}
            return data.get("snapshot_id")

    async def fetch_playlist_tracks(pl_id: str) -> List[dict]:
        items: List[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Request additional album fields for release date
            url = f"https://api.spotify.com/v1/playlists/{pl_id}/tracks?limit=100&fields=items(added_at,track(id,name,artists,album(name,images,release_date,release_date_precision),duration_ms,external_ids,explicit)),next"
            while url:
                resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
                if resp.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Spotify API error: {resp.text}")
                data = resp.json()
                items.extend(data.get("items", []))
                url = data.get("next")
        return items

    # Build identity index to minimize queries (optional micro-optimization omitted for clarity)
    total_created = total_updated = total_linked = total_removed = 0
    summaries = []

    for pl in target_playlists:
        created = updated = linked = removed = 0

        # Determine if playlist snapshot changed; fetch remote snapshot first
        remote_snapshot: Optional[str] = None
        if pl.provider_playlist_id:
            try:
                remote_snapshot = await fetch_playlist_snapshot(pl.provider_playlist_id)
            except HTTPException:
                # If snapshot fetch fails, fall back to full sync attempt (raise original later if track fetch fails)
                remote_snapshot = None

        # Skip only if snapshot unchanged AND the playlist already has links
        # This avoids skipping the very first sync in cases where a snapshot was
        # persisted during discovery but tracks were never ingested yet.
        should_skip = False
        if pl.snapshot and remote_snapshot and pl.snapshot == remote_snapshot:
            # Check if any PlaylistTrack rows already exist for this playlist
            result_count = await session.execute(
                select(func.count(PlaylistTrack.id)).where(PlaylistTrack.playlist_id == pl.id)
            )
            has_links = (result_count.scalar() or 0) > 0
            should_skip = has_links

        if should_skip:
            summaries.append({
                "playlist_id": pl.id,
                "provider_playlist_id": pl.provider_playlist_id,
                "name": pl.name,
                "tracks_created": 0,
                "tracks_updated": 0,
                "links_created": 0,
                "links_removed": 0,
                "skipped": True,
            })
            continue

        items = await fetch_playlist_tracks(pl.provider_playlist_id or "")

        # Track position based on returned order
        pos = 0
        # Collect Spotify track ids to batch fetch audio features after initial upsert
        sp_track_ids: list[str] = []
        # Map provider_track_id -> (Track, added_at_dt)
        track_refs: dict[str, tuple[Track, Optional[Any]]] = {}
        new_playlist_track_ids: set[int] = set()
        for it in items:
            tr = (it or {}).get("track") or {}
            if not tr or tr.get("id") is None:
                continue
            pos += 1

            sp_track_id: str = tr.get("id")
            title: str = tr.get("name") or ""
            artists_list = tr.get("artists") or []
            artists_names = ", ".join([a.get("name") for a in artists_list if a and a.get("name")])
            album_data = tr.get("album") or {}
            album = album_data.get("name")
            images = album_data.get("images") or []
            duration_ms = tr.get("duration_ms")
            isrc = None
            ext_ids = tr.get("external_ids") or {}
            if isinstance(ext_ids, dict):
                isrc = ext_ids.get("isrc")
            
            # Extract release date from album
            release_date = None
            release_date_raw = album_data.get("release_date")
            if isinstance(release_date_raw, str) and release_date_raw:
                try:
                    from datetime import datetime
                    # Spotify release_date can be YYYY, YYYY-MM, or YYYY-MM-DD
                    release_date_precision = album_data.get("release_date_precision", "day")
                    if release_date_precision == "year" and len(release_date_raw) == 4:
                        # Only year: set to January 1st
                        release_date = datetime(int(release_date_raw), 1, 1)
                    elif release_date_precision == "month" and len(release_date_raw) == 7:
                        # Year-Month: set to first day of month
                        year, month = release_date_raw.split("-")
                        release_date = datetime(int(year), int(month), 1)
                    elif release_date_precision == "day" and len(release_date_raw) == 10:
                        # Full date
                        release_date = datetime.fromisoformat(release_date_raw)
                    else:
                        # Fallback: try to parse as-is
                        release_date = datetime.fromisoformat(release_date_raw)
                except Exception:
                    release_date = None
            
            added_at_raw = it.get("added_at")
            added_at = None
            if isinstance(added_at_raw, str) and added_at_raw:
                # Convert ISO8601 with possible 'Z' suffix to timezone-aware datetime
                try:
                    from datetime import datetime
                    iso = added_at_raw.replace("Z", "+00:00") if added_at_raw.endswith("Z") else added_at_raw
                    added_at = datetime.fromisoformat(iso)
                except Exception:
                    added_at = None

            # Find existing track via identity
            result = await session.execute(
                select(TrackIdentity, Track)
                .join(Track, Track.id == TrackIdentity.track_id)
                .where(
                    TrackIdentity.provider == SourceProvider.spotify,
                    TrackIdentity.provider_track_id == sp_track_id,
                )
            )
            row = result.first()
            if row:
                identity, track = row
                # Update minimal fields to reflect latest metadata
                before = (track.title, track.artists, track.album, track.duration_ms, track.isrc, track.release_date)
                track.title = title or track.title
                track.artists = artists_names or track.artists
                track.album = album or track.album
                track.duration_ms = duration_ms or track.duration_ms
                track.isrc = isrc or track.isrc
                # Update release_date if we have a new one and the track doesn't have one yet, or if the new one is different
                if release_date and (not track.release_date or track.release_date != release_date):
                    track.release_date = release_date
                # Normalize if changed
                after = (track.title, track.artists, track.album, track.duration_ms, track.isrc, track.release_date)
                if after != before:
                    n = normalize_track(track.artists, track.title)
                    track.normalized_artists = n.normalized_artists
                    track.normalized_title = n.normalized_title
                    updated += 1
                # Prefer Spotify album art if none set
                if not track.cover_url and images:
                    best = max(images, key=lambda im: im.get("width") or 0)
                    if best and best.get("url"):
                        track.cover_url = best.get("url")
            else:
                # Create new track and identity
                n = normalize_track(artists_names, title)
                track = Track(
                    title=title or "",
                    artists=artists_names or "",
                    album=album,
                    duration_ms=duration_ms,
                    isrc=isrc,
                    explicit=bool(tr.get("explicit")) if tr.get("explicit") is not None else False,
                    cover_url=(max(images, key=lambda im: im.get("width") or 0).get("url") if images else None),
                    normalized_title=n.normalized_title,
                    normalized_artists=n.normalized_artists,
                    release_date=release_date,
                    # created_at will be overwritten below if we have added_at earlier
                )
                session.add(track)
                await session.flush()
                identity = TrackIdentity(
                    track_id=track.id,
                    provider=SourceProvider.spotify,
                    provider_track_id=sp_track_id,
                    provider_url=f"https://open.spotify.com/track/{sp_track_id}",
                )
                session.add(identity)
                created += 1

            # Potentially adjust created_at to playlist added_at if earlier (keeping earliest known ingestion date)
            # Normalize timezone differences: DB naive vs Spotify UTC aware
            if added_at and track.created_at:
                try:
                    cmp_added = added_at
                    cmp_created = track.created_at
                    if cmp_added.tzinfo is not None and cmp_created.tzinfo is None:
                        # make added_at naive for comparison
                        cmp_added = cmp_added.replace(tzinfo=None)
                    elif cmp_added.tzinfo is None and cmp_created.tzinfo is not None:
                        # make created_at naive (copy) for comparison
                        cmp_created = cmp_created.replace(tzinfo=None)
                    if cmp_added < cmp_created:
                        # assign stored created_at using same naive/aware style as existing field to avoid mixing
                        track.created_at = cmp_added if track.created_at.tzinfo else cmp_added.replace(tzinfo=None)
                except Exception:
                    pass  # comparison failures are non-fatal

            # Stash ref for audio features batch fetch
            sp_track_ids.append(sp_track_id)
            track_refs[sp_track_id] = (track, added_at)

            # Ensure playlist exists and link
            if pl.source_account_id is None:
                pl.source_account_id = account_id
            # Position and added_at mapping
            result = await session.execute(
                select(PlaylistTrack).where(
                    PlaylistTrack.playlist_id == pl.id,
                    PlaylistTrack.track_id == track.id,
                )
            )
            link = result.scalars().first()
            if not link:
                link = PlaylistTrack(
                    playlist_id=pl.id,
                    track_id=track.id,
                    position=pos,
                    added_at=added_at,
                )
                session.add(link)
                linked += 1
            else:
                # Update position on incremental sync (e.g., reorders)
                link.position = pos
                # If added_at not persisted yet and remote provides one, capture it
                if added_at and not link.added_at:
                    link.added_at = added_at
            new_playlist_track_ids.add(track.id)

        # Audio feature enrichment removed (Spotify endpoint not available / deprecated for this application)

        # Detect removals: any existing link not in new set
        result_links = await session.execute(
            select(PlaylistTrack).where(PlaylistTrack.playlist_id == pl.id)
        )
        for existing_link in result_links.scalars().all():
            if existing_link.track_id not in new_playlist_track_ids:
                await session.delete(existing_link)
                removed += 1

        # Update stored snapshot after successful sync
        if remote_snapshot:
            pl.snapshot = remote_snapshot

        summaries.append({
            "playlist_id": pl.id,
            "provider_playlist_id": pl.provider_playlist_id,
            "name": pl.name,
            "tracks_created": created,
            "tracks_updated": updated,
            "links_created": linked,
            "links_removed": removed,
            "skipped": False,
        })
        total_created += created
        total_updated += updated
        total_linked += linked
        total_removed += removed

    return {
        "playlists": summaries,
        "total_tracks_created": total_created,
        "total_tracks_updated": total_updated,
        "total_links_created": total_linked,
        "total_links_removed": total_removed,
    }
@router.get("/{playlist_id}/entries")
async def list_playlist_entries(
    playlist_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return playlist entries with track details, ordered by position.

    Response shape: [{ position, added_at, track: TrackRead }]
    """
    # Ensure playlist exists
    pl = await session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")

    result = await session.execute(
        select(PlaylistTrack, Track)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position.asc())
    )
    rows = result.all()
    out: List[Dict[str, Any]] = []
    for pt, tr in rows:
        # Serialize track using existing schema for consistent fields
        try:
            tr_json = TrackRead.model_validate(tr).model_dump()  # type: ignore[attr-defined]
        except Exception:
            # Fallback: manual minimal fields
            tr_json = {
                "id": tr.id,
                "title": tr.title,
                "artists": tr.artists,
                "album": tr.album,
                "duration_ms": tr.duration_ms,
                "isrc": tr.isrc,
                "year": tr.year,
                "explicit": tr.explicit,
                "cover_url": tr.cover_url,
                "normalized_title": tr.normalized_title,
                "normalized_artists": tr.normalized_artists,
                "genre": tr.genre,
                "bpm": tr.bpm,
                "created_at": tr.created_at,
                "updated_at": tr.updated_at,
            }
        out.append({
            "position": pt.position,
            "added_at": pt.added_at.isoformat() if pt.added_at else None,
            "track": tr_json,
        })
    return out


@router.post("/memberships")
async def playlists_memberships(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_session),
):
    """Return playlist memberships for given track ids.

    Body: { "track_ids": [1,2,...] }

    Response: { track_id: [ { playlist_id, playlist_name, position }, ... ], ... }
    """
    ids = list(body.get("track_ids") or [])
    if not ids:
        return {}
    result = await session.execute(
        select(PlaylistTrack, Playlist)
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .where(PlaylistTrack.track_id.in_(ids))
    )
    rows = result.all()
    out: Dict[int, List[Dict[str, Any]]] = {}
    for pt, pl in rows:
        out.setdefault(pt.track_id, []).append({
            "playlist_id": pl.id,
            "playlist_name": pl.name,
            "position": pt.position,
        })
    # Sort memberships by playlist name then position
    for k, arr in out.items():
        arr.sort(key=lambda x: (x.get("playlist_name") or "", x.get("position") or 0))
    return out
