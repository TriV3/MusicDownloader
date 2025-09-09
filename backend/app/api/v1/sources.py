from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import SourceAccount  # type: ignore
    from ...schemas.models import SourceAccountCreate, SourceAccountRead  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import SourceAccount  # type: ignore
    from schemas.models import SourceAccountCreate, SourceAccountRead  # type: ignore


router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/accounts", response_model=List[SourceAccountRead])
async def list_accounts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(SourceAccount))
    return result.scalars().all()


@router.post("/accounts", response_model=SourceAccountRead)
async def create_account(payload: SourceAccountCreate, session: AsyncSession = Depends(get_session)):
    account = SourceAccount(**payload.model_dump())
    session.add(account)
    await session.flush()
    return account


@router.get("/accounts/{account_id}", response_model=SourceAccountRead)
async def get_account(account_id: int, session: AsyncSession = Depends(get_session)):
    account = await session.get(SourceAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="SourceAccount not found")
    return account
