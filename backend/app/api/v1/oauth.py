from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import OAuthToken  # type: ignore
    from ...schemas.models import OAuthTokenCreate, OAuthTokenRead  # type: ignore
    from ...utils.crypto import encrypt_text  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import OAuthToken  # type: ignore
    from schemas.models import OAuthTokenCreate, OAuthTokenRead  # type: ignore
    from utils.crypto import encrypt_text  # type: ignore


router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/tokens", response_model=List[OAuthTokenRead])
async def list_tokens(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(OAuthToken))
    return result.scalars().all()


@router.post("/tokens", response_model=OAuthTokenRead)
async def create_token(payload: OAuthTokenCreate, session: AsyncSession = Depends(get_session)):
    refresh_enc = None
    if payload.refresh_token:
        refresh_enc = encrypt_text(payload.refresh_token)
    token = OAuthToken(
        source_account_id=payload.source_account_id,
        provider=payload.provider,
        access_token=payload.access_token,
        refresh_token_encrypted=refresh_enc,
        scope=payload.scope,
        token_type=payload.token_type,
        expires_at=payload.expires_at,
    )
    session.add(token)
    await session.flush()
    return token
