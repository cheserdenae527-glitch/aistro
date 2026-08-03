"""门店 + 平台店铺 CRUD API。"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.merchant import Merchant
from app.models.platform_shop import PlatformShop
from app.models.shop import Shop
from app.models.user import User
from app.schemas.platform_shop import PlatformShopCreate, PlatformShopResponse
from app.schemas.merchant import MerchantResponse
from app.schemas.shop import ShopCreate, ShopResponse, ShopUpdate

router = APIRouter(tags=["shops"])


@router.get("/profile/merchants-with-shops")
async def profile_index(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """装修首页一次性返回商家及其门店，避免 N+1 串行请求。"""
    merchants = (
        await db.execute(
            select(Merchant)
            .where(Merchant.user_id == current_user.id)
            .order_by(Merchant.created_at)
        )
    ).scalars().all()
    if not merchants:
        return []

    shops = (
        await db.execute(
            select(Shop)
            .where(Shop.merchant_id.in_([m.id for m in merchants]))
            .order_by(Shop.created_at)
        )
    ).scalars().all()
    shops_by_merchant: dict = defaultdict(list)
    for shop in shops:
        shops_by_merchant[shop.merchant_id].append(ShopResponse.model_validate(shop))

    return [
        {
            "merchant": MerchantResponse.model_validate(m),
            "shops": shops_by_merchant.get(m.id, []),
        }
        for m in merchants
    ]


async def _get_merchant_or_404(
    mid: str, user: User, db: AsyncSession
) -> Merchant:
    result = await db.execute(
        select(Merchant).where(Merchant.id == mid, Merchant.user_id == user.id)
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


async def _get_shop_or_404(sid: str, db: AsyncSession) -> Shop:
    result = await db.execute(select(Shop).where(Shop.id == sid))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


# ---- 嵌套路由（列表/创建） ----

@router.get("/merchants/{mid}/shops")
async def list_shops(
    mid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_merchant_or_404(mid, current_user, db)
    result = await db.execute(
        select(Shop).where(Shop.merchant_id == mid).order_by(Shop.created_at)
    )
    return [ShopResponse.model_validate(s) for s in result.scalars().all()]


@router.post("/merchants/{mid}/shops", response_model=ShopResponse, status_code=201)
async def create_shop(
    mid: str,
    body: ShopCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_merchant_or_404(mid, current_user, db)
    shop = Shop(merchant_id=mid, **body.model_dump(exclude_unset=True))
    db.add(shop)
    await db.flush()
    return ShopResponse.model_validate(shop)


# ---- 扁平路由（门店读写） ----

@router.get("/shops/{sid}", response_model=ShopResponse)
async def get_shop(
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _get_shop_or_404(sid, db)
    return ShopResponse.model_validate(shop)


@router.patch("/shops/{sid}", response_model=ShopResponse)
async def update_shop(
    sid: str,
    body: ShopUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _get_shop_or_404(sid, db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(shop, k, v)
    await db.flush()
    return ShopResponse.model_validate(shop)


@router.delete("/shops/{sid}", status_code=204)
async def delete_shop(
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _get_shop_or_404(sid, db)
    await db.delete(shop)


# ---- 平台店铺绑定 ----

@router.get("/shops/{sid}/platforms")
async def list_platforms(
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_shop_or_404(sid, db)
    result = await db.execute(
        select(PlatformShop).where(PlatformShop.shop_id == sid)
    )
    return [PlatformShopResponse.model_validate(p) for p in result.scalars().all()]


@router.post("/shops/{sid}/platforms", response_model=PlatformShopResponse, status_code=201)
async def create_platform(
    sid: str,
    body: PlatformShopCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_shop_or_404(sid, db)
    plat = PlatformShop(shop_id=sid, **body.model_dump(exclude_unset=True))
    db.add(plat)
    await db.flush()
    return PlatformShopResponse.model_validate(plat)
