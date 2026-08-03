"""口碑管理模块 API — 评价列表/摘要/同步/分析/AI 回复/预警处理。

鉴权：全部 JWT + shop 所有权（shop -> merchant -> user），非所有者 404。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.review_agent import ReviewAgent
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import check_rate_limit, peek_rate_limit, set_rate_limit
from app.core.sensitive_filter import contains_blocked
from app.models.merchant import Merchant
from app.models.platform_shop import PlatformShop
from app.models.review import Review
from app.models.shop import Shop
from app.models.user import User
from app.schemas.review import (
    AiReplyResponse,
    AlertAckResponse,
    BatchAnalyzeItem,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    ReplyUpdateRequest,
    ReputationSummaryResponse,
    ReviewListResponse,
    ReviewResponse,
    SyncResponse,
    SyncXiaohongshuRequest,
)
from app.services.reputation import apply_sentiment_alert, mark_manual_replied
from app.services.review_sync import XhsSyncError, sync_xhs_comments, sync_xhs_notes

router = APIRouter(tags=["reputation"])


# ============================================================
# 鉴权与资源 helper
# ============================================================


async def _verify_shop_owner(
    shop_id: str, user: User, db: AsyncSession
) -> Shop:
    result = await db.execute(
        select(Shop)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Shop.id == shop_id, Merchant.user_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def _get_review_for_shop(
    rid: str, shop: Shop, db: AsyncSession
) -> Review:
    try:
        rid_uuid = uuid.UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Review not found")
    result = await db.execute(
        select(Review)
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(Review.id == rid_uuid, PlatformShop.shop_id == shop.id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


def _rate_key(action: str, user: User, shop: Shop) -> str:
    return f"rate_limit:{action}:{user.id}:{shop.id}"


def _sync_error_detail(error: str) -> str:
    low = error.lower()
    if not error:
        return "爬虫同步失败，请稍后重试"
    if "登录" in error or "login" in low or "未登录" in error:
        return f"登录态失效，请更新 cookie（{error}）"
    if any(
        token in low
        for token in ("xsec", "token", "expire", "过期", "失效", "permission")
    ):
        return f"笔记链接已过期，请重新同步该笔记（{error}）"
    return error


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ============================================================
# 评价列表 / 摘要
# ============================================================


@router.get(
    "/shops/{shop_id}/reviews",
    response_model=ReviewListResponse,
)
async def list_reviews(
    shop_id: str,
    review_type: Literal["note", "comment", "rating_review"] | None = Query(None),
    sentiment: Literal["positive", "neutral", "negative"] | None = Query(None),
    reply_status: Literal["unreplied", "ai_replied", "manual_replied"] | None = Query(None),
    alert_status: Literal["none", "triggered", "acknowledged"] | None = Query(None),
    keyword: str | None = Query(None, max_length=100),
    parent_review_id: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    base = (
        select(Review)
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(PlatformShop.shop_id == shop.id)
    )
    count_base = (
        select(func.count(Review.id))
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(PlatformShop.shop_id == shop.id)
    )

    if review_type:
        base = base.where(Review.review_type == review_type)
        count_base = count_base.where(Review.review_type == review_type)
    if sentiment:
        base = base.where(Review.sentiment == sentiment)
        count_base = count_base.where(Review.sentiment == sentiment)
    if reply_status:
        base = base.where(Review.reply_status == reply_status)
        count_base = count_base.where(Review.reply_status == reply_status)
    if alert_status:
        base = base.where(Review.alert_status == alert_status)
        count_base = count_base.where(Review.alert_status == alert_status)
    if parent_review_id:
        try:
            parent_uuid = uuid.UUID(parent_review_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="parent_review_id 格式无效")
        base = base.where(Review.parent_review_id == parent_uuid)
        count_base = count_base.where(Review.parent_review_id == parent_uuid)
    if keyword:
        pattern = f"%{keyword}%"
        cond = or_(
            Review.content.ilike(pattern),
            Review.note_title.ilike(pattern),
        )
        base = base.where(cond)
        count_base = count_base.where(cond)
    if date_from:
        base = base.where(Review.reviewed_at >= date_from)
        count_base = count_base.where(Review.reviewed_at >= date_from)
    if date_to:
        base = base.where(Review.reviewed_at <= date_to)
        count_base = count_base.where(Review.reviewed_at <= date_to)

    total = (await db.execute(count_base)).scalar_one()
    rows = await db.execute(
        base.order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return ReviewListResponse(
        items=[ReviewResponse.model_validate(r) for r in rows.scalars().all()],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/shops/{shop_id}/reviews/summary",
    response_model=ReputationSummaryResponse,
)
async def review_summary(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    shop_cond = PlatformShop.shop_id == shop.id

    async def _count(*conds) -> int:
        stmt = (
            select(func.count(Review.id))
            .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
            .where(shop_cond, *conds)
        )
        return int((await db.execute(stmt)).scalar_one())

    note_count = await _count(Review.review_type == "note")
    comment_count = await _count(Review.review_type == "comment")
    rating_review_count = await _count(Review.review_type == "rating_review")
    unreplied_count = await _count(
        Review.review_type == "comment",
        Review.reply_status == "unreplied",
    )
    alert_count = await _count(Review.alert_status == "triggered")

    sentiment_rows = await db.execute(
        select(Review.sentiment, func.count(Review.id))
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(shop_cond)
        .group_by(Review.sentiment)
    )
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0, "unanalyzed": 0}
    for sentiment_value, count in sentiment_rows.all():
        key = sentiment_value if sentiment_value in sentiment_counts else "unanalyzed"
        sentiment_counts[key] = int(count)

    return ReputationSummaryResponse(
        note_count=note_count,
        comment_count=comment_count,
        rating_review_count=rating_review_count,
        sentiment_counts=sentiment_counts,
        unreplied_count=unreplied_count,
        alert_count=alert_count,
    )


# ============================================================
# XHS 同步
# ============================================================


@router.post(
    "/shops/{shop_id}/reviews/sync/xiaohongshu",
    response_model=SyncResponse,
)
async def sync_xiaohongshu_notes(
    shop_id: str,
    body: SyncXiaohongshuRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    if not await check_rate_limit(
        _rate_key("sync_notes", current_user, shop), ttl_seconds=60
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后重试")
    try:
        created, skipped = await sync_xhs_notes(shop, db, body.keyword, body.limit)
    except XhsSyncError as exc:
        raise HTTPException(status_code=502, detail=_sync_error_detail(str(exc)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"笔记同步失败：{exc}")
    return SyncResponse(created=created, skipped=skipped)


@router.post(
    "/shops/{shop_id}/reviews/{rid}/sync-comments",
    response_model=SyncResponse,
)
async def sync_note_comments(
    shop_id: str,
    rid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    review = await _get_review_for_shop(rid, shop, db)
    if review.review_type != "note":
        raise HTTPException(status_code=400, detail="仅笔记支持同步评论")

    rate_key = _rate_key("sync_comments", current_user, shop) + f":{review.id}"
    if not await check_rate_limit(rate_key, ttl_seconds=60):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后重试")
    try:
        created, skipped = await sync_xhs_comments(shop, db, review)
    except XhsSyncError as exc:
        raise HTTPException(status_code=502, detail=_sync_error_detail(str(exc)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"评论同步失败：{exc}")
    return SyncResponse(created=created, skipped=skipped)


# ============================================================
# 批量情感分析
# ============================================================


@router.post(
    "/shops/{shop_id}/reviews/batch-analyze",
    response_model=BatchAnalyzeResponse,
)
async def batch_analyze(
    shop_id: str,
    body: BatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    if len(body.review_ids) > 20:
        raise HTTPException(status_code=400, detail="单次最多分析 20 条")
    if not await check_rate_limit(
        _rate_key("batch_analyze", current_user, shop), ttl_seconds=30
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 30 秒后重试")

    result = await db.execute(
        select(Review)
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(
            PlatformShop.shop_id == shop.id,
            Review.id.in_(body.review_ids),
        )
    )
    reviews = result.scalars().all()
    by_id = {review.id: review for review in reviews}
    requested = set(body.review_ids)
    failed: list[uuid.UUID] = list(requested - set(by_id))

    analyzed: list[BatchAnalyzeItem] = []
    agent = ReviewAgent()
    ordered_ids = [rid for rid in body.review_ids if rid in by_id]
    for chunk in _chunks(ordered_ids, 10):
        chunk_reviews = [by_id[rid] for rid in chunk]
        try:
            items = await agent.analyze_batch(chunk_reviews)
        except Exception:
            failed.extend(chunk)
            continue
        analyzed_ids: set[uuid.UUID] = set()
        for item in items:
            review = by_id.get(item.id)
            if review is None or item.id not in chunk:
                continue
            review.sentiment = item.sentiment
            review.tags = item.tags
            apply_sentiment_alert(review, item.sentiment)
            analyzed_ids.add(item.id)
            analyzed.append(
                BatchAnalyzeItem(
                    id=item.id,
                    sentiment=item.sentiment,
                    tags=item.tags,
                )
            )
        failed.extend(rid for rid in chunk if rid not in analyzed_ids)

    await db.flush()
    return BatchAnalyzeResponse(
        analyzed=analyzed,
        failed=failed,
        total=len(body.review_ids),
        success_count=len(analyzed),
        failed_count=len(failed),
    )


# ============================================================
# AI 回复草稿 / 确认回复
# ============================================================


@router.post(
    "/shops/{shop_id}/reviews/{rid}/ai-reply",
    response_model=AiReplyResponse,
)
async def generate_ai_reply(
    shop_id: str,
    rid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    review = await _get_review_for_shop(rid, shop, db)
    if review.review_type != "comment":
        raise HTTPException(status_code=400, detail="仅评论可生成回复草稿")
    if contains_blocked(review.content or ""):
        raise HTTPException(status_code=422, detail="评论内容包含敏感词，请重新生成")

    rate_key = _rate_key("ai_reply", current_user, shop)
    if not await peek_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后重试")

    agent = ReviewAgent()
    try:
        draft = await agent.generate_reply(
            content=review.content or "",
            shop_name=shop.name,
            category=shop.category,
            positioning=shop.category,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="回复草稿生成失败，请稍后重试")
    if contains_blocked(draft):
        raise HTTPException(status_code=422, detail="生成内容包含敏感词，请重新生成")

    # LLM 成功路径才写入频控 key，敏感词 422 不占窗口。
    await set_rate_limit(rate_key, ttl_seconds=20)
    review.ai_reply = draft
    review.reply_status = "ai_replied"
    await db.flush()
    return AiReplyResponse(id=review.id, ai_reply=draft)


@router.put(
    "/shops/{shop_id}/reviews/{rid}/reply",
    response_model=ReviewResponse,
)
async def confirm_reply(
    shop_id: str,
    rid: str,
    body: ReplyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    review = await _get_review_for_shop(rid, shop, db)
    if review.review_type == "note":
        raise HTTPException(status_code=400, detail="笔记不参与回复")

    review.reply_content = body.reply_content
    review.reply_status = "manual_replied"
    review.replied_at = datetime.now(timezone.utc)
    mark_manual_replied(review)
    await db.flush()
    return ReviewResponse.model_validate(review)


# ============================================================
# 差评预警
# ============================================================


@router.get(
    "/shops/{shop_id}/reviews/alerts",
    response_model=list[ReviewResponse],
)
async def list_alerts(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    result = await db.execute(
        select(Review)
        .join(PlatformShop, Review.platform_shop_id == PlatformShop.id)
        .where(
            PlatformShop.shop_id == shop.id,
            Review.alert_status == "triggered",
        )
        .order_by(Review.created_at.desc(), Review.id.desc())
    )
    return [ReviewResponse.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/shops/{shop_id}/reviews/alerts/{rid}/ack",
    response_model=AlertAckResponse,
)
async def acknowledge_alert(
    shop_id: str,
    rid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)
    review = await _get_review_for_shop(rid, shop, db)
    if review.alert_status == "none":
        raise HTTPException(status_code=400, detail="该记录尚未触发预警，无需处理")
    if review.alert_status == "triggered":
        review.alert_status = "acknowledged"
        await db.flush()
    return AlertAckResponse(id=review.id, alert_status=review.alert_status)
