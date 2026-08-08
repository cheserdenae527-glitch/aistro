"""订阅博主 API — CRUD + 状态查询 + 更新提醒。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subscription import Subscription, SubscriptionSnapshot
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionStatusBatchRequest,
    SubscriptionStatusBatchResponse,
    SubscriptionStatusItem,
    SnapshotResponse,
)
from app.services.subscription_service import refresh_subscription
from app.services.xhs_runtime import get_xhs_api

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _has_update(sub: Subscription) -> bool:
    return sub.note_count > sub.notified_note_count


@router.get("")
async def list_subs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(desc(Subscription.created_at))
    )
    return [SubscriptionResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_sub(
    body: SubscriptionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.xhs_user_id == body.xhs_user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="已订阅")
    sub = Subscription(user_id=user.id, **body.model_dump())
    db.add(sub)
    await db.flush()
    return SubscriptionResponse.model_validate(sub)


@router.post("/{sub_id}/refresh", response_model=SubscriptionResponse)
async def refresh_sub(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    return await refresh_subscription(db, sub)


@router.delete("/{sub_id}", status_code=204)
async def delete_sub(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(sub)


@router.get("/{sub_id}/notes")
async def get_sub_notes(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    from crawler.processor import normalize_note
    from crawler.gate import gate

    try:
        await asyncio.to_thread(gate.wait)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    api = await asyncio.to_thread(get_xhs_api)
    success, msg, raw_notes = await asyncio.to_thread(
        api.get_user_all_notes,
        f"https://www.xiaohongshu.com/user/profile/{sub.xhs_user_id}",
    )
    if not success:
        if gate.is_risk_error(str(msg)):
            gate.note_failure(str(msg))
        raise HTTPException(status_code=502, detail=str(msg))
    if not raw_notes:
        return {"notes": [], "nickname": sub.nickname}
    for n in raw_notes:
        n.setdefault("id", n.get("note_id", ""))
    notes = [normalize_note(n) for n in raw_notes[:50]]
    return {"notes": notes, "nickname": sub.nickname}


@router.get("/{sub_id}/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Not found")
    snapshots = await db.execute(
        select(SubscriptionSnapshot)
        .where(SubscriptionSnapshot.subscription_id == sub_id)
        .order_by(desc(SubscriptionSnapshot.crawled_at))
        .limit(30)
    )
    return [SnapshotResponse.model_validate(s) for s in snapshots.scalars().all()]


@router.get("/status", response_model=SubscriptionStatusItem)
async def get_sub_status(
    xhs_user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单个博主订阅状态，供订阅按钮渲染。"""
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.xhs_user_id == xhs_user_id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return SubscriptionStatusItem(subscribed=False)
    return SubscriptionStatusItem(
        subscribed=True,
        subscription_id=sub.id,
        has_update=_has_update(sub),
    )


@router.post("/status/batch", response_model=SubscriptionStatusBatchResponse)
async def batch_sub_status(
    body: SubscriptionStatusBatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量查询订阅状态，避免列表页 N+1 请求。"""
    ids = list(dict.fromkeys(body.xhs_user_ids))
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.xhs_user_id.in_(ids),
        )
    )
    items: dict[str, SubscriptionStatusItem] = {
        xhs_id: SubscriptionStatusItem(subscribed=False) for xhs_id in ids
    }
    for sub in result.scalars().all():
        items[sub.xhs_user_id] = SubscriptionStatusItem(
            subscribed=True,
            subscription_id=sub.id,
            has_update=_has_update(sub),
        )
    return SubscriptionStatusBatchResponse(items=items)


@router.post("/{sub_id}/ack", response_model=SubscriptionResponse)
async def ack_sub_update(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看后清除"有更新"标记。"""
    result = await db.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    sub.notified_note_count = sub.note_count
    await db.flush()
    return SubscriptionResponse.model_validate(sub)
