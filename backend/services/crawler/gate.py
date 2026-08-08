"""全局防风控门禁 — 请求节流 + 熔断 + 风险识别。

所有 XHS 请求统一经过 gate：
- 任意两次请求之间至少间隔 min_interval 秒（进程内全局，跨爬虫实例/调度器生效）
- 短时间连续命中风控特征（x-rap-param 失败、data:null、登录失效等）触发熔断，
  熔断期间直接拒绝新请求，避免继续触发平台限流
"""
from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger("crawler.gate")

RISK_KEYWORDS = (
    "x-rap-param",
    "noneType",
    "data:null",
    "data: none",
    "登录",
    "login",
    "风控",
    "频繁",
    "操作过快",
    "rate limit",
    "risk",
    "访问过于频繁",
    "账号异常",
    "captcha",
    "验证",
    "滑块",
    "verify",
    "暂时无法浏览",
    "无法浏览",
    "内容不存在",
    "300031",
)


class RiskGate:
    def __init__(
        self,
        min_interval: float = 1.5,
        failure_threshold: int = 3,
        cooldown: float = 180.0,
    ):
        self._lock = threading.Lock()
        self._last_ok_at = 0.0
        self._failures: list[float] = []
        self._open_until = 0.0
        self._min_interval = float(min_interval)
        self._failure_threshold = int(failure_threshold)
        self._cooldown = float(cooldown)

    def is_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._open_until

    def wait(self) -> None:
        """等待到允许下一次请求；熔断开启时抛 RuntimeError。"""
        if self.is_open():
            raise RuntimeError("小红书风控熔断中，请稍后重试")
        with self._lock:
            elapsed = time.monotonic() - self._last_ok_at
            wait = max(0.0, self._min_interval - elapsed) + random.uniform(0.2, 0.6)
        if wait > 0:
            time.sleep(wait)

    def mark_request(self) -> None:
        with self._lock:
            self._last_ok_at = time.monotonic()

    def note_success(self) -> None:
        with self._lock:
            self._last_ok_at = time.monotonic()
            self._failures = []

    def note_failure(self, message: str = "") -> None:
        with self._lock:
            now = time.monotonic()
            self._failures = [t for t in self._failures if now - t < 60.0]
            self._failures.append(now)
            if len(self._failures) >= self._failure_threshold:
                self._open_until = now + self._cooldown
                logger.warning(
                    "风控熔断开启 %.0fs（连续 %d 次失败）",
                    self._cooldown,
                    len(self._failures),
                )
                self._failures = []

    @staticmethod
    def is_risk_error(message: str) -> bool:
        if not message:
            return False
        low = str(message).lower()
        return any(kw.lower() in low for kw in RISK_KEYWORDS)

    @staticmethod
    def classify_risk_error(message: str) -> str:
        """把风控错误分类为 risk_type（data_null/captcha/x_rap_param/login_expired/rate_limit/other）。"""
        low = str(message or "").lower()
        if not low:
            return "other"
        if "x-rap-param" in low:
            return "x_rap_param"
        if "data:null" in low or "data: none" in low or "nonetype" in low:
            return "data_null"
        if "captcha" in low or "滑块" in low or "验证" in low or "verify" in low:
            return "captcha"
        if "暂时无法浏览" in low or "无法浏览" in low or "内容不存在" in low or "300031" in low:
            return "content_unavailable"
        if "登录" in low or "login" in low:
            return "login_expired"
        if any(k in low for k in ("rate limit", "频繁", "操作过快", "访问过于频繁", "风控", "risk", "账号异常")):
            return "rate_limit"
        return "other"


def _build_gate() -> RiskGate:
    try:
        from crawler.config import load_config

        cfg = load_config()
    except Exception:
        cfg = {}
    return RiskGate(
        min_interval=float(cfg.get("risk_min_interval", 1.5)),
        failure_threshold=int(cfg.get("risk_failure_threshold", 3)),
        cooldown=float(cfg.get("risk_cooldown_seconds", 180)),
    )


gate = _build_gate()
