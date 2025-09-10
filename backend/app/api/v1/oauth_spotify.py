from __future__ import annotations

import base64
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import OAuthState, OAuthToken, SourceAccount, SourceProvider  # type: ignore
    from ...schemas.models import OAuthTokenRead  # type: ignore
    from ...utils.crypto import encrypt_text, decrypt_text  # type: ignore
    from ...core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import OAuthState, OAuthToken, SourceAccount, SourceProvider  # type: ignore
    from schemas.models import OAuthTokenRead  # type: ignore
    from utils.crypto import encrypt_text, decrypt_text  # type: ignore
    from core.config import settings  # type: ignore


router = APIRouter(prefix="/oauth/spotify", tags=["oauth", "spotify"])

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env {name}")
    return value


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _gen_pkce() -> tuple[str, str]:
    code_verifier = _b64url(os.urandom(32))
    # RFC 7636 S256
    import hashlib

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = _b64url(digest)
    return code_verifier, code_challenge


@router.get("/authorize")
async def authorize(
    account_id: int = Query(..., description="SourceAccount id for Spotify"),
    redirect_to: Optional[str] = Query(None, description="Front URL to redirect after success"),
    session: AsyncSession = Depends(get_session),
):
    # Validate account
    account = await session.get(SourceAccount, account_id)
    if not account or account.type != SourceProvider.spotify:
        raise HTTPException(status_code=404, detail="Spotify account not found")

    client_id = settings.spotify_client_id or _get_env("SPOTIFY_CLIENT_ID")
    redirect_uri = settings.spotify_redirect_uri or _get_env("SPOTIFY_REDIRECT_URI")

    code_verifier, code_challenge = _gen_pkce()
    state = secrets.token_urlsafe(16)

    # Persist OAuthState
    oauth_state = OAuthState(
        provider=SourceProvider.spotify,
        source_account_id=account_id,
        state=state,
        code_verifier=code_verifier,
        redirect_to=redirect_to,
    )
    session.add(oauth_state)
    await session.flush()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "playlist-read-private playlist-read-collaborative user-read-email",  # adjust scopes
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"authorize_url": url}


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session),
):
    client_id = settings.spotify_client_id or _get_env("SPOTIFY_CLIENT_ID")
    client_secret = settings.spotify_client_secret or _get_env("SPOTIFY_CLIENT_SECRET")
    redirect_uri = settings.spotify_redirect_uri or _get_env("SPOTIFY_REDIRECT_URI")

    # Lookup OAuthState
    result = await session.execute(select(OAuthState).where(OAuthState.state == state))
    oauth_state: Optional[OAuthState] = result.scalars().first()
    if not oauth_state or oauth_state.consumed:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Exchange code for tokens
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": oauth_state.code_verifier,
        # For confidential clients, Spotify requires client_secret
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(SPOTIFY_TOKEN_URL, data=data)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")
        tok = resp.json()

    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    expires_in = tok.get("expires_in", 3600)
    scope = tok.get("scope")
    token_type = tok.get("token_type")

    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in response")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Upsert OAuthToken for this account
    result = await session.execute(
        select(OAuthToken).where(
            OAuthToken.source_account_id == oauth_state.source_account_id,
            OAuthToken.provider == SourceProvider.spotify,
        )
    )
    existing: Optional[OAuthToken] = result.scalars().first()
    if existing:
        existing.access_token = access_token
        existing.scope = scope
        existing.token_type = token_type
        existing.expires_at = expires_at
        if refresh_token:
            existing.refresh_token_encrypted = encrypt_text(refresh_token)
    else:
        session.add(
            OAuthToken(
                source_account_id=oauth_state.source_account_id,
                provider=SourceProvider.spotify,
                access_token=access_token,
                refresh_token_encrypted=encrypt_text(refresh_token) if refresh_token else None,
                scope=scope,
                token_type=token_type,
                expires_at=expires_at,
            )
        )

    oauth_state.consumed = True
    oauth_state.used_at = datetime.now(timezone.utc)

    # Redirect handling is frontend concern; here we return JSON including redirect target
    return {"status": "ok", "redirect_to": oauth_state.redirect_to}


@router.post("/refresh", response_model=OAuthTokenRead)
async def refresh(account_id: int, session: AsyncSession = Depends(get_session)):
    client_id = settings.spotify_client_id or _get_env("SPOTIFY_CLIENT_ID")
    client_secret = settings.spotify_client_secret or _get_env("SPOTIFY_CLIENT_SECRET")

    result = await session.execute(
        select(OAuthToken).where(
            OAuthToken.source_account_id == account_id,
            OAuthToken.provider == SourceProvider.spotify,
        )
    )
    token: Optional[OAuthToken] = result.scalars().first()
    if not token or not token.refresh_token_encrypted:
        raise HTTPException(status_code=404, detail="No token/refresh_token for this account")

    refresh_token = decrypt_text(token.refresh_token_encrypted)

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(SPOTIFY_TOKEN_URL, data=data)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Refresh failed: {resp.text}")
        tok = resp.json()

    access_token = tok.get("access_token")
    expires_in = tok.get("expires_in", 3600)
    scope = tok.get("scope")
    token_type = tok.get("token_type")
    new_refresh = tok.get("refresh_token")  # sometimes not returned

    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in refresh response")

    token.access_token = access_token
    token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    if scope:
        token.scope = scope
    if token_type:
        token.token_type = token_type
    if new_refresh:
        token.refresh_token_encrypted = encrypt_text(new_refresh)

    await session.flush()
    return token
