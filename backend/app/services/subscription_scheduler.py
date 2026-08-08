"""订阅定时刷新调度器 — 进程内 APScheduler，预留 Celery Beat 替换点。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import desc, select

from app.core.database import async_session_factory
from app.models.note_detail import NoteDetail
from app.models.subscription import Subscription, SubscriptionSnapshot
from app.services.analysis_task_runner import _upsert_detail
from app.services.subscription_service import refresh_subscription
from crawler.config import load_config

logger = logging.getLogger("crawler.subscription_scheduler")


class SubscriptionScheduler:
    """按配置间隔批量刷新订阅，复用手动 refresh 服务方法。"""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        cfg = load_config()
        interval_hours = float(cfg.get("subscription_refresh_interval_hours", 12))
        self._scheduler.add_job(
            self._refresh_job,
            IntervalTrigger(hours=interval_hours),
            id="subscription_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info("SubscriptionScheduler started, interval=%sh", interval_hours)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False

    @staticmethod
    def _crawler():
        from app.api.v1.notes import _get_crawler

        return _get_crawler(min_delay=1.0, max_delay=2.0, max_retries=1)

    async def _should_deep_sync(self, sub: Subscription) -> bool:
        cfg = load_config()
        interval_hours = float(cfg.get("subscription_deep_sync_min_interval_hours", 24))
        now = datetime.now(timezone.utc)
        if sub.last_deep_synced_at and (now - sub.last_deep_synced_at).total_seconds() < interval_hours * 3600:
            return False
        async with async_session_factory() as db:
            result = await db.execute(
                select(SubscriptionSnapshot)
                .where(SubscriptionSnapshot.subscription_id == sub.id)
                .order_by(desc(SubscriptionSnapshot.crawled_at))
                .limit(2)
            )
            snaps = list(result.scalars().all())
        return len(snaps) >= 2 and snaps[0].note_count > snaps[1].note_count

    async def _deep_sync_subscription(self, sub: Subscription) -> None:
        """增量抓取新增笔记详情写入 note_details，供分析任务复用。"""
        cfg = load_config()
        max_run = int(cfg.get("subscription_deep_sync_max_per_run", 200))
        crawler = self._crawler()
        user_url = f"https://www.xiaohongshu.com/user/profile/{sub.xhs_user_id}"
        result = await asyncio.to_thread(crawler.get_user_notes, user_url)
        if not result.success:
            logger.warning("深度同步获取列表失败 sub=%s: %s", sub.id, result.error)
            return
        raw = result.data or []
        async with async_session_factory() as db:
            existing = await db.execute(
                select(NoteDetail.platform_note_id).where(NoteDetail.xhs_user_id == sub.xhs_user_id)
            )
            known = set(existing.scalars().all())
        missing: list[tuple[str, str]] = []
        for n in raw:
            nid = n.get("note_id") or n.get("id")
            if nid and nid not in known:
                missing.append((str(nid), str(n.get("xsec_token", "") or "")))
            if len(missing) >= max_run:
                break

        from crawler.processor import normalize_note
        from app.api.v1.notes import _extract_detail_items

        count = 0
        for nid, token in missing:
            if not token:
                continue
            url = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_user"
            detail = await asyncio.to_thread(crawler.get_note_detail, url)
            items = _extract_detail_items(detail)
            if items:
                norm = normalize_note(items[0])
                norm["full_stats"] = True
                async with async_session_factory() as db:
                    await _upsert_detail(db, sub.xhs_user_id, nid, norm)
                    await db.commit()
                count += 1
        async with async_session_factory() as db:
            row = await db.get(Subscription, sub.id)
            if row:
                row.last_deep_synced_at = datetime.now(timezone.utc)
                await db.commit()
        logger.info("深度详情同步完成 sub=%s 新增=%d", sub.id, count)

    async def _refresh_job(self) -> None:
        cfg = load_config()
        batch_size = int(cfg.get("subscription_refresh_batch_size", 20))
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Subscription)
                    .order_by(Subscription.last_crawled_at.asc().nullsfirst())
                    .limit(batch_size)
                )
                subs = list(result.scalars().all())
            if not subs:
                return
            for sub in subs:
                try:
                    async with async_session_factory() as db:
                        await refresh_subscription(db, sub)
                        await db.commit()
                except Exception as exc:
                    logger.warning("订阅刷新失败 sub=%s: %s", sub.id, exc)
                await asyncio.sleep(3)
                try:
                    if await self._should_deep_sync(sub):
                        await self._deep_sync_subscription(sub)
                except Exception as exc:
                    logger.warning("订阅深度同步失败 sub=%s: %s", sub.id, exc)
                await asyncio.sleep(3)
        except Exception as exc:
            logger.exception("订阅定时刷新任务异常: %s", exc)
