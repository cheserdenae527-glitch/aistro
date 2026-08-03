"""商家 CRUD API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.merchant import Merchant
from app.models.user import User
from app.schemas.merchant import MerchantCreate, MerchantResponse, MerchantUpdate

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("")
async def list_merchants(
    page: int = 1,
    size: int = 20,
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Merchant).where(Merchant.user_id == current_user.id)
    count_query = select(func.count(Merchant.id)).where(Merchant.user_id == current_user.id)
    if name:
        pattern = f"%{name}%"
        query = query.where(Merchant.name.ilike(pattern))
        count_query = count_query.where(Merchant.name.ilike(pattern))
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset((page - 1) * size).limit(size))
    items = [MerchantResponse.model_validate(m) for m in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    body: MerchantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    merchant = Merchant(
        user_id=current_user.id,
        **body.model_dump(exclude_unset=True),
    )
    db.add(merchant)
    await db.flush()
    return MerchantResponse.model_validate(merchant)


@router.get("/{mid}", response_model=MerchantResponse)
async def get_merchant(
    mid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return MerchantResponse.model_validate(merchant)


@router.patch("/{mid}", response_model=MerchantResponse)
async def update_merchant(
    mid: str,
    body: MerchantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(merchant, k, v)
    await db.flush()
    return MerchantResponse.model_validate(merchant)


@router.delete("/{mid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merchant(
    mid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    await db.delete(merchant)
