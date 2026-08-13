"""Cookie 池健康检查调度器 — 定期主动探测各 Cookie 登录态，失效自动降级。

背景：XHS Cookie 登录态可能随时间失效（登录已过期），失效 Cookie 会让批量任务成片失败。
本调度器每隔 cookie_check_interval_minutes 对池内 Cookie 做一次轻量探测（搜索接口），
发现"登录过期"即走 cookie_pool.report_result 冷却/淘汰链路，让池子自动避开失效号。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from crawler import cookie_pool
from crawler.config import get_proxy_pool, load_config

logger = logging.getLogger("crawler.cookie_health")

# 命中即判定 Cookie 登录态失效
_EXPIRED_KEYWORDS = ("登录已过期", "登录过期", "cookie 已失效", "账号失效", "登录失效")
# 命中即跳过（属于风控/熔断/网络，不应误杀 Cookie）
_SKIP_KEYWORDS = ("熔断", "风控", "频率", "频繁", "timeout", "timed out", "407", "proxy")


class CookieHealthScheduler:
    """按配置间隔探测 Cookie 池登录态。"""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        cfg = load_config()
        interval_minutes = float(cfg.get("cookie_check_interval_minutes", 60))
        self._scheduler.add_job(
            self._check_job,
            IntervalTrigger(minutes=interval_minutes),
            id="cookie_health_check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info("CookieHealthScheduler started, interval=%smin", interval_minutes)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False

    @staticmethod
    def _build_crawler(cookie_id: str):
        from crawler.xhs import XhsCrawler

        entry = cookie_pool.get_cookie_entry(cookie_id)
        if not entry or not entry.get("cookie"):
            return None
        proxy = entry.get("proxy") or {}
        now = int(__import__("time").time())
        expires = int(entry.get("proxy_expires_at") or 0)
        if proxy.get("http") and (not expires or expires > now):
            return XhsCrawler(entry["cookie"], proxies=proxy, cookie_id=cookie_id)
        return XhsCrawler(entry["cookie"], proxy_pool=get_proxy_pool(), cookie_id=cookie_id)

    async def _check_job(self) -> None:
        """遍历池内 Cookie 逐个探测；串行，避免同时触发风控。"""
        cookies = cookie_pool.list_cookies()
        if not cookies:
            return
        healthy, expired, skipped = 0, 0, 0
        for c in cookies:
            cid = c.get("id")
            if not cid or not c.get("cookie") or c.get("status") != "available":
                continue
            try:
                crawler = self._build_crawler(cid)
                if crawler is None:
                    continue
                # 用 check_cookie（get_user_self_info）真正验证登录态；搜索接口可能游客可用，无法区分登录过期
                ok = await __import__("asyncio").to_thread(crawler.check_cookie)
            except Exception as exc:  # 探测异常不判定 Cookie 失效
                logger.warning("Cookie 探测异常 cookie=%s: %s", cid, exc)
                skipped += 1
                continue
            if ok:
                cookie_pool.report_result(cid, True)
                healthy += 1
            else:
                # check_cookie 失败：登录过期/网络/风控都会返回 False；连续 2 次才冷却、恢复即清零，
                # 且登录过期会持续失败 → 冷却→淘汰，因此误杀风险低
                cookie_pool.report_result(cid, False, "登录态探测失败（check_cookie）")
                logger.warning("Cookie 登录态探测失败已降级 cookie=%s", cid)
                expired += 1
        logger.info("Cookie 健康检查完成：健康 %d / 失效 %d / 跳过 %d", healthy, expired, skipped)
