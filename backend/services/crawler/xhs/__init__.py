"""
AiRestro XHS 爬虫封装层 — 含防风控策略。

策略：
- 随机延时 + 指数退避
- 失败自动重试
- 代理池轮换
- Cookie 健康检测
- 请求频率限制
"""

from __future__ import annotations

import os
import sys
import time
import random
import logging

from crawler.base import BaseCrawler, CrawlResult

logger = logging.getLogger("crawler.xhs")

_RUNTIME = os.path.join(os.path.dirname(__file__), "scripts", "runtime", "spider_xhs_core")
_XSEC_SOURCES = ["pc_search", "pc_feed", "pc_user", "pc_detail"]

DEFAULT_MIN_DELAY = 2.0
DEFAULT_MAX_DELAY = 5.0
DEFAULT_RETRIES = 3
BACKOFF_BASE = 2.0
BACKOFF_CAP = 30.0


class XhsCrawler(BaseCrawler):
    """小红书爬虫（防风控版）。"""

    def __init__(
        self,
        cookies_str: str,
        proxies: dict | None = None,
        proxy_pool: list[dict] | None = None,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        max_retries: int = DEFAULT_RETRIES,
    ):
        self._cookies_str = cookies_str
        self._proxies = proxies
        self._proxy_pool = proxy_pool or []
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._auth = None
        self._api = None
        self._last_request_at = 0.0
        self._proxy_idx = 0

    def _ensure_init(self):
        if self._api is not None:
            return
        # ensure node is in PATH for the backend process
        node_dir = r"C:\Program Files\nodejs"
        if node_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = node_dir + os.pathsep + os.environ.get("PATH", "")
            return
        old_cwd = os.getcwd()
        os.chdir(_RUNTIME)
        if _RUNTIME not in sys.path:
            sys.path.insert(0, _RUNTIME)
        try:
            from xhs_utils.xhs_pc import XHSPcAuth
            from apis.xhs_pc_apis import XHS_Apis
            self._auth = XHSPcAuth.from_cookie(self._cookies_str, proxies=self._current_proxy())
            self._api = XHS_Apis(self._auth)
        finally:
            os.chdir(old_cwd)

    def _current_proxy(self) -> dict | None:
        if self._proxy_pool:
            p = self._proxy_pool[self._proxy_idx % len(self._proxy_pool)]
            self._proxy_idx += 1
            return p
        return self._proxies

    def _throttle(self):
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self._min_delay:
            wait = self._min_delay - elapsed + random.uniform(0.5, 1.5)
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _backoff(self, attempt: int):
        exp = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
        wait = exp * random.uniform(0.8, 1.2)
        logger.info("请求失败，%.1fs 后重试 (第 %d 次)", wait, attempt + 1)
        time.sleep(wait)

    def _execute(self, fn, *args, **kwargs) -> CrawlResult:
        """带重试的执行包装。fn 返回 (success, msg, data)。"""
        self._throttle()
        last_err = None
        for attempt in range(self._max_retries):
            try:
                success, msg, data = fn(*args, **kwargs)
                if success:
                    return CrawlResult(success=True, data=data or [])
                last_err = msg
                if last_err and ("登录" in str(last_err) or "login" in str(last_err).lower()):
                    logger.warning("Cookie 已过期: %s", last_err)
                    return CrawlResult(success=False, error=str(last_err))
            except Exception as e:
                last_err = str(e)
            if attempt < self._max_retries - 1:
                self._backoff(attempt)
        return CrawlResult(success=False, error=str(last_err) if last_err else "Unknown error")

    @staticmethod
    def build_note_url(note: dict) -> str:
        nid = note.get("id", "")
        token = note.get("xsec_token", "")
        source = random.choice(_XSEC_SOURCES)
        return f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source={source}"

    def check_cookie(self) -> bool:
        try:
            self._ensure_init()
            success, msg, data = self._api.get_user_self_info()
            return bool(success)
        except Exception as e:
            logger.error("Cookie 检测失败: %s", e)
            return False

    def search_notes(self, query: str, limit: int = 20, sort_type: int = 0, note_type: int = 0, time_range: int = 0) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.search_some_note,
            query, limit,
            sort_type_choice=sort_type,
            note_type=note_type,
            note_time=time_range,
            proxies=self._current_proxy(),
        )

    def get_note_detail(self, note_url: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_note_info,
            note_url,
            proxies=self._current_proxy(),
        )

    def get_comments(self, note_url: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_note_all_comment,
            note_url,
            proxies=self._current_proxy(),
        )

    def get_user_info(self, user_id: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_user_info,
            user_id,
            proxies=self._current_proxy(),
        )

    def get_user_notes(self, user_url: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_user_all_notes,
            user_url,
            proxies=self._current_proxy(),
        )
