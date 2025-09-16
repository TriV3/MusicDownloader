from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Playlist, SourceProvider, SourceAccount, OAuthToken  # type: ignore
    from ...schemas.models import PlaylistCreate, PlaylistRead  # type: ignore
    from ...core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Playlist, SourceProvider, SourceAccount, OAuthToken  # type: ignore
    from schemas.models import PlaylistCreate, PlaylistRead  # type: ignore
    from core.config import settings  # type: ignore

import os
import httpx


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


@router.get("/{playlist_id}", response_model=PlaylistRead)
async def get_playlist(playlist_id: int, session: AsyncSession = Depends(get_session)):
    playlist = await session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env {name}")
    return value


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
