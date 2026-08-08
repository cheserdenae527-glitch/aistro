"""速率限制 — 进程内实现（替代 Redis，不依赖 Docker）。

单进程本地部署足够，对外 4 个函数语义与原 Redis 版本一致：
- check_rate_limit / set_rate_limit：NX 型窗口（key 存在即限流）
- consume_rate_limit：最近 window_seconds 内最多 limit 次
- peek_rate_limit：只检查不占窗口
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
# key -> expire_at（NX 型频控）
_exclusive: dict[str, float] = {}
# key -> [timestamp, ...]（计数型频控）
_counts: dict[str, list[float]] = {}


def _reset() -> None:
    """清空全部进程内频控状态（测试用）。"""
    _exclusive.clear()
    _counts.clear()


async def check_rate_limit(key: str, ttl_seconds: int = 20) -> bool:
    """检查并占用频控窗口。返回 True = 允许通过，False = 已限流。"""
    async with _lock:
        now = time.monotonic()
        expire_at = _exclusive.get(key)
        if expire_at is not None and expire_at > now:
            return False
        _exclusive[key] = now + ttl_seconds
        return True


async def consume_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """固定窗口计数限流。返回 True = 允许，False = 超限。"""
    async with _lock:
        now = time.monotonic()
        stamps = [t for t in _counts.get(key, []) if now - t < window_seconds]
        if len(stamps) >= limit:
            _counts[key] = stamps
            return False
        stamps.append(now)
        _counts[key] = stamps
        return True


async def peek_rate_limit(key: str) -> bool:
    """只检查频控 key 是否存在，不占窗口。True = 未限流。"""
    async with _lock:
        now = time.monotonic()
        expire_at = _exclusive.get(key)
        return expire_at is None or expire_at <= now


async def set_rate_limit(key: str, ttl_seconds: int = 20) -> None:
    """在成功路径上显式写入频控窗口。"""
    async with _lock:
        _exclusive[key] = time.monotonic() + ttl_seconds