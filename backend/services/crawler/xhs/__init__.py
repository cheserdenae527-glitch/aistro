"""
AiRestro XHS 爬虫封装层 — 含防风控策略。

策略（v1.4 起）：
- 随机延时 + 指数退避（仅网络错误重试）
- 风控类错误不重试，直接熔断计数（避免同账号/IP 继续试探放大风险）
- 会话级固定代理：一次采集操作（含其重试）使用同一代理，跨操作轮换
- Cookie 健康检测
- 请求频率限制（全局 gate）
- 请求结果观测：写入 crawl_request_log.jsonl，支撑风控参数校准（方案 §1.4 / 附录 A）
"""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
import threading
import time
import logging

from crawler.base import BaseCrawler, CrawlResult
from crawler.gate import gate, RiskGate

logger = logging.getLogger("crawler.xhs")

_RUNTIME = os.path.join(os.path.dirname(__file__), "scripts", "runtime", "spider_xhs_core")
_XSEC_SOURCES = ["pc_search", "pc_feed", "pc_user", "pc_detail"]

DEFAULT_MIN_DELAY = 3.0
DEFAULT_MAX_DELAY = 6.0
DEFAULT_RETRIES = 3
BACKOFF_BASE = 2.0
BACKOFF_CAP = 30.0
_INIT_LOCK = threading.Lock()
_PROXY_PICK_LOCK = threading.Lock()
_PROXY_PICK_INDEX = 0


def _pick_proxy(pool: list[dict]) -> dict | None:
    """跨爬虫实例全局轮换代理池，保证不同 worker/请求尽量使用不同出口 IP。"""
    global _PROXY_PICK_INDEX
    if not pool:
        return None
    with _PROXY_PICK_LOCK:
        proxy = pool[_PROXY_PICK_INDEX % len(pool)]
        _PROXY_PICK_INDEX += 1
        return proxy


def _proxy_short_label(proxy: dict | None) -> str:
    """从 proxies 里提取 host:port，用于请求日志区分出口 IP。"""
    if not proxy:
        return ""
    for key in ("http", "https"):
        url = str(proxy.get(key) or "")
        if "@" in url:
            return url.rsplit("@", 1)[-1]
        if url:
            return url
    return ""


def _looks_like_proxy_error(message: str) -> bool:
    low = str(message or "").lower()
    return (
        "407" in low
        or "connect tunnel failed" in low
        or "proxy authentication" in low
        or "proxy connect error" in low
        or "connection refused" in low
    )


# ── 请求观测日志（JSONL，append；线程安全）──
_REQUEST_LOG_PATH = os.path.join(os.path.dirname(__file__), "scripts", "crawl_request_log.jsonl")
_REQUEST_LOG_LOCK = threading.Lock()


def _log_request(
    *,
    job_type: str = "unknown",
    target: str = "",
    result: str = "ok",
    risk_type: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    interval_before_ms: int | None = None,
    proxy_used: str | None = None,
    cookie_id: str | None = None,
) -> None:
    """追加一条请求观测记录；观测失败不影响采集主流程。"""
    try:
        record = {
            "ts_ms": int(time.time() * 1000),
            "channel": "redcrack",
            "job_type": job_type,
            "target": str(target)[:255],
            "result": result,
            "risk_type": risk_type,
            "error_message": str(error_message)[:500] if error_message else None,
            "latency_ms": latency_ms,
            "interval_before_ms": interval_before_ms,
            "proxy_used": proxy_used,
            "cookie_id": cookie_id,
        }
        with _REQUEST_LOG_LOCK:
            with open(_REQUEST_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        cookie_id: str | None = None,
    ):
        self._cookies_str = cookies_str
        self._cookie_id = cookie_id
        self._proxies = proxies
        self._proxy_pool = proxy_pool or []
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._auth = None
        self._api = None
        self._last_request_at = 0.0
        self._active_proxy = None  # 会话级固定代理（一次采集操作内不变）

    def _ensure_init(self):
        with _INIT_LOCK:
            if self._api is not None:
                return
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node.js 未安装，无法初始化小红书爬虫")
            node_dir = os.path.dirname(node)
            if node_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = node_dir + os.pathsep + os.environ.get("PATH", "")
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
        """会话级固定代理：首次调用选定后缓存，跨重试保持不变（跨任务轮换）。"""
        if self._active_proxy is not None:
            return self._active_proxy
        if self._proxy_pool:
            p = _pick_proxy(self._proxy_pool)
            self._active_proxy = p
            return p
        self._active_proxy = self._proxies
        return self._proxies

    def _throttle(self):
        # 全局节流：跨爬虫实例/调度器统一限频
        gate.wait()
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

    def _execute(self, fn, *args, job_type: str = "unknown", target: str = "", **kwargs) -> CrawlResult:
        """带重试的执行包装。fn 返回 (success, msg, data)。

        风控策略（v1.4）：
        - 风控类错误（data:null / 验证码 / x-rap-param / 登录失效）→ 不重试，立即返回并计入熔断
        - 仅网络/超时类错误 → 指数退避重试
        - 会话级固定代理：本次操作（含重试）复用同一代理
        """
        # 会话级固定代理（一次采集操作 + 其重试共用），操作结束后释放以便轮换
        kwargs["proxies"] = self._current_proxy()
        try:
            return self._execute_impl(fn, *args, job_type=job_type, target=target, **kwargs)
        finally:
            self._active_proxy = None

    def _execute_impl(self, fn, *args, job_type: str = "unknown", target: str = "", **kwargs) -> CrawlResult:
        """真正的执行体；代理由 _execute 统一选定并在结束后释放。"""
        proxy_used = _proxy_short_label(self._active_proxy)
        if gate.is_open():
            _log_request(job_type=job_type, target=target, result="circuit_open", proxy_used=proxy_used, cookie_id=self._cookie_id)
            return CrawlResult(success=False, error="小红书风控熔断中，请稍后重试")

        def _mark_cookie(success: bool, error: str = "") -> None:
            if not self._cookie_id:
                return
            try:
                from crawler.cookie_pool import report_result

                report_result(self._cookie_id, success, error)
            except Exception:
                pass

        throttle_started = time.monotonic()
        try:
            self._throttle()
        except RuntimeError as exc:
            _log_request(job_type=job_type, target=target, result="circuit_open", error_message=str(exc), proxy_used=proxy_used, cookie_id=self._cookie_id)
            return CrawlResult(success=False, error=str(exc))
        interval_before_ms = int((time.monotonic() - throttle_started) * 1000)

        last_err = None
        for attempt in range(self._max_retries):
            started = time.monotonic()
            try:
                gate.mark_request()
                success, msg, data = fn(*args, **kwargs)
                latency_ms = int((time.monotonic() - started) * 1000)
                if success:
                    gate.note_success()
                    _mark_cookie(True)
                    _log_request(job_type=job_type, target=target, result="ok", latency_ms=latency_ms, interval_before_ms=interval_before_ms, proxy_used=proxy_used, cookie_id=self._cookie_id)
                    return CrawlResult(success=True, data=data or [])
                last_err = msg
                risk = RiskGate.is_risk_error(str(last_err))
                _log_request(
                    job_type=job_type, target=target,
                    result="risk_signal" if risk else "http_error",
                    risk_type=RiskGate.classify_risk_error(str(last_err)) if risk else None,
                    error_message=str(last_err), latency_ms=latency_ms, interval_before_ms=interval_before_ms,
                    proxy_used=proxy_used,
                    cookie_id=self._cookie_id,
                )
                if risk:
                    # 风控信号：不重试，立即返回，避免继续试探放大风险
                    gate.note_failure(str(last_err))
                    _mark_cookie(False, str(last_err))
                    logger.warning("风控信号（%s），不重试: %s", RiskGate.classify_risk_error(str(last_err)), last_err)
                    return CrawlResult(success=False, error=str(last_err))
                if "登录" in str(last_err) or "login" in str(last_err).lower():
                    _mark_cookie(False, str(last_err))
                    logger.warning("Cookie 已过期: %s", last_err)
                    return CrawlResult(success=False, error=str(last_err))
            except Exception as e:
                last_err = str(e)
                latency_ms = int((time.monotonic() - started) * 1000)
                risk = RiskGate.is_risk_error(str(last_err))
                _log_request(
                    job_type=job_type, target=target,
                    result="risk_signal" if risk else "network_error",
                    risk_type=RiskGate.classify_risk_error(str(last_err)) if risk else None,
                    error_message=str(last_err), latency_ms=latency_ms, interval_before_ms=interval_before_ms,
                    proxy_used=proxy_used,
                    cookie_id=self._cookie_id,
                )
                if risk:
                    gate.note_failure(str(last_err))
                    _mark_cookie(False, str(last_err))
                    logger.warning("风控信号（%s），不重试: %s", RiskGate.classify_risk_error(str(last_err)), last_err)
                    return CrawlResult(success=False, error=str(last_err))
            if attempt < self._max_retries - 1:
                self._backoff(attempt)
        if self._cookie_id and _looks_like_proxy_error(last_err):
            try:
                from crawler.cookie_pool import report_proxy_result

                report_proxy_result(self._cookie_id, False)
            except Exception:
                pass
        return CrawlResult(success=False, error=str(last_err) if last_err else "Unknown error")

    @staticmethod
    def build_note_url(note: dict) -> str:
        nid = note.get("id", "")
        token = note.get("xsec_token", "")
        source = random.choice(_XSEC_SOURCES)
        return f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source={source}"

    def check_cookie(self) -> bool:
        """验证登录态：走 _execute 调 user/me（bootstrap），复用会话代理/风控门禁，
        登录过期由 _execute 内部 _mark_cookie 回写（report_result 冷却/淘汰）。"""
        try:
            self._ensure_init()
            result = self._execute(self._api.bootstrap, job_type="user_info", target="cookie_check")
            return bool(result.success)
        except Exception as e:
            logger.error("Cookie 检测失败: %s", e)
            return False

    def search_users(self, query: str, limit: int = 20) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.search_some_user, query, limit,
            job_type="search_users", target=query,
        )

    def search_notes(self, query: str, limit: int = 20, sort_type: int = 0, note_type: int = 0, time_range: int = 0) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.search_some_note, query, limit,
            sort_type_choice=sort_type, note_type=note_type, note_time=time_range,
            job_type="search", target=query,
        )

    def get_note_detail(self, note_url: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_note_info, note_url,
            job_type="note_detail", target=note_url,
        )

    def get_comments(self, note_url: str) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_note_all_comment, note_url,
            job_type="comment", target=note_url,
        )

    def get_user_info(self, user_id: str, xsec_token: str = "", xsec_source: str = "pc_search") -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_user_info, user_id,
            xsec_token=xsec_token, xsec_source=xsec_source,
            job_type="user_info", target=user_id,
        )

    def get_user_notes(self, user_url: str, max_notes: int = 0) -> CrawlResult:
        self._ensure_init()
        return self._execute(
            self._api.get_user_all_notes, user_url, max_notes=max_notes,
            job_type="blogger", target=user_url,
        )
