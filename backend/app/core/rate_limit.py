"""速率限制 — 基于 Redis 的简单频控。"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.core.config import settings

_pool: aioredis.ConnectionPool | None = None
logger = logging.getLogger(__name__)


def _get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2.0,
            socket_timeout=1.0,
            retry_on_timeout=False,
        )
    return aioredis.Redis(connection_pool=_pool)


async def check_rate_limit(
    key: str, ttl_seconds: int = 20
) -> bool:
    """检查频控。

    返回 True = 允许通过（key 不存在，已设置）
    返回 False = 触发限流
    """
    r = _get_redis()
    try:
        ok = await r.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(ok)
    except Exception:
        # Redis 不可用时放行，避免装修/生图功能整体不可用。
        logger.warning("Redis 不可用，频控已跳过: %s", key)
        return True


async def consume_rate_limit(
    key: str, limit: int, window_seconds: int
) -> bool:
    """固定窗口计数限流，Redis 不可用时放行。"""
    r = _get_redis()
    try:
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window_seconds)
        return count <= limit
    except Exception:
        logger.warning("Redis 不可用，计数限流已跳过: %s", key)
        return True


async def peek_rate_limit(key: str) -> bool:
    """只检查频控 key 是否存在，不占窗口。

    返回 True = 未限流；False = 已限流。
    """
    r = _get_redis()
    try:
        return not bool(await r.exists(key))
    except Exception:
        logger.warning("Redis 不可用，频控检查已跳过: %s", key)
        return True


async def set_rate_limit(key: str, ttl_seconds: int = 20) -> None:
    """在成功路径上显式写入频控 key。"""
    r = _get_redis()
    try:
        await r.set(key, "1", ex=ttl_seconds, nx=True)
    except Exception:
        logger.warning("Redis 不可用，频控写入已跳过: %s", key)
