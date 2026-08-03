"""口碑 XHS 同步服务 — 笔记/评论去重落库 + 落库时关键词预警。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.review_agent import scan_alert_keywords
from app.models.platform_shop import PlatformShop
from app.models.review import Review
from app.models.shop import Shop
from app.services.reputation import trigger_keyword_alert


class XhsSyncError(Exception):
    """爬虫同步失败，error 保留原始信息用于 API 错误区分。"""


def build_xhs_crawler():
    from crawler.config import get_cookie, get_delay_settings, get_proxy_pool
    from crawler.xhs import XhsCrawler

    cookie = get_cookie()
    if not cookie:
        raise XhsSyncError("未配置小红书 Cookie")
    proxies = get_proxy_pool()
    min_delay, max_delay, max_retries = get_delay_settings()
    return XhsCrawler(
        cookie,
        proxy_pool=proxies,
        min_delay=min_delay,
        max_delay=max_delay,
        max_retries=max_retries,
    )


async def get_or_create_xhs_platform_shop(
    shop: Shop, db: AsyncSession
) -> PlatformShop:
    result = await db.execute(
        select(PlatformShop)
        .where(
            PlatformShop.shop_id == shop.id,
            PlatformShop.platform == "xiaohongshu",
        )
        .order_by(PlatformShop.created_at)
    )
    platform_shop = result.scalars().first()
    if platform_shop is not None:
        return platform_shop
    platform_shop = PlatformShop(
        shop_id=shop.id,
        platform="xiaohongshu",
        platform_shop_id="xiaohongshu",
        shop_name=shop.name,
    )
    db.add(platform_shop)
    await db.flush()
    return platform_shop


async def sync_xhs_notes(
    shop: Shop,
    db: AsyncSession,
    keyword: str,
    limit: int = 20,
) -> tuple[int, int]:
    """搜索小红书笔记并去重落库，返回 (created, skipped)。"""
    from crawler.processor import normalize_note
    from crawler.xhs import XhsCrawler

    crawler = build_xhs_crawler()
    result = crawler.search_notes(keyword, limit=limit)
    if not result.success:
        raise XhsSyncError(result.error or "笔记搜索失败")

    platform_shop = await get_or_create_xhs_platform_shop(shop, db)
    note_ids = [n.get("id") for n in result.data if n.get("id")]
    if not note_ids:
        return 0, 0
    existing_rows = await db.execute(
        select(Review.platform_review_id).where(
            Review.platform_shop_id == platform_shop.id,
            Review.review_type == "note",
            Review.platform_review_id.in_(note_ids),
        )
    )
    existing = set(existing_rows.scalars().all())

    created = 0
    skipped = 0
    for note in result.data:
        note_id = note.get("id")
        if not note_id:
            continue
        normalized = normalize_note(note)
        if note_id in existing:
            skipped += 1
            continue

        title = normalized["title"] or ""
        desc = normalized["desc"] or ""
        keywords = scan_alert_keywords(f"{title} {desc}")
        review = Review(
            platform_shop_id=platform_shop.id,
            platform_review_id=note_id,
            review_type="note",
            reviewer_name=normalized["author"]["nickname"],
            content=desc,
            note_title=title[:200],
            note_url=XhsCrawler.build_note_url(note),
            author_id=normalized["author"]["id"],
            author_avatar=normalized["author"]["avatar"],
            interact_stats=normalized["stats"],
            source_json=normalized["raw"],
            rating=None,
            reply_status=None,
            reviewed_at=None,
        )
        if keywords:
            trigger_keyword_alert(review, keywords)
        db.add(review)
        existing.add(note_id)
        created += 1

    platform_shop.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    return created, skipped


def _parse_reviewed_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = value
        if ts > 10_000_000_000:  # 毫秒时间戳
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _flatten_comments(raw: dict) -> list[dict]:
    """把顶层评论与嵌套回复统一拍平成评论列表。"""
    from crawler.processor import normalize_comment

    normalized = normalize_comment(raw)
    flat = [normalized]
    for sub in normalized.get("sub_comments") or []:
        if isinstance(sub, dict):
            flat.extend(_flatten_comments(sub))
    return flat


async def sync_xhs_comments(
    shop: Shop,
    db: AsyncSession,
    note_review: Review,
) -> tuple[int, int]:
    """拉取笔记评论并去重落库，返回 (created, skipped)。"""
    if not note_review.note_url:
        raise XhsSyncError("笔记缺少链接，无法同步评论")

    crawler = build_xhs_crawler()
    result = crawler.get_comments(note_review.note_url)
    if not result.success:
        raise XhsSyncError(result.error or "评论拉取失败")

    platform_shop = await get_or_create_xhs_platform_shop(shop, db)
    raw_ids = [c.get("id") for c in result.data if c.get("id")]
    if not raw_ids:
        return 0, 0
    comment_rows = await db.execute(
        select(Review.platform_review_id).where(
            Review.platform_shop_id == platform_shop.id,
            Review.review_type == "comment",
            Review.platform_review_id.in_(raw_ids),
        )
    )
    existing = set(comment_rows.scalars().all())

    created = 0
    skipped = 0
    for raw_comment in result.data:
        comment_id = raw_comment.get("id")
        if not comment_id:
            continue
        for normalized in _flatten_comments(raw_comment):
            platform_comment_id = normalized["platform_comment_id"]
            if not platform_comment_id:
                continue
            if platform_comment_id in existing:
                skipped += 1
                continue

            content = normalized["content"] or ""
            keywords = scan_alert_keywords(content)
            review = Review(
                platform_shop_id=platform_shop.id,
                platform_review_id=platform_comment_id,
                review_type="comment",
                parent_review_id=note_review.id,
                reviewer_name=normalized["author"]["nickname"],
                content=content,
                author_id=normalized["author"]["id"],
                author_avatar=normalized["author"]["avatar"],
                interact_stats={"liked": normalized["liked"]},
                source_json=normalized["raw"],
                rating=None,
                reply_status="unreplied",
                reviewed_at=_parse_reviewed_at(normalized["created_at"]),
            )
            if keywords:
                trigger_keyword_alert(review, keywords)
            db.add(review)
            existing.add(platform_comment_id)
            created += 1

    platform_shop.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    return created, skipped
