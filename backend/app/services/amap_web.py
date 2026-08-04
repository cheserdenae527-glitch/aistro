"""高德开放平台 Web API 服务 — 地理编码 + 周边搜索 + 日配额保护。

产品功能统一走 Web API（AMAP_WEB_API_KEY）；MCP（app.services.amap_mcp）
仅供深度调研辅助，不参与商圈分析产品链路。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.rate_limit import consume_rate_limit

logger = logging.getLogger(__name__)

_AMAP_BASE = "https://restapi.amap.com/v3"
_GEOCODE_URL = f"{_AMAP_BASE}/geocode/geo"
_AROUND_URL = f"{_AMAP_BASE}/place/around"
_SECURITY_CONFIG_URL = "https://restapi.amap.com/securityConfig"

# 地理编码精度白名单（白名单放行，其余一律拒绝）
_GEOCODE_LEVEL_ALLOWED = {"门牌号", "道路", "兴趣点", "地名"}

# 餐饮服务类型
_TYPES_FOOD = "050000"

_PAGE_SIZE = 25
_MAX_PAGES = 4
_RETRY_DELAY = 0.2  # 瞬时错误重试前退避（秒）

_DAILY_QUOTA_KEY_PREFIX = "amap_daily_quota:"


class AmapWebError(Exception):
    """高德 Web API 调用失败，携带 HTTP 状态码与提示。"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def daily_quota_key() -> str:
    """按 Asia/Shanghai 自然日生成配额 key（与高德北京时间配额对齐）。"""
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    return f"{_DAILY_QUOTA_KEY_PREFIX}{today}"


async def _consume_daily_quota() -> None:
    ok = await consume_rate_limit(
        daily_quota_key(),
        limit=settings.AMAP_DAILY_QUOTA_LIMIT,
        window_seconds=86400,
    )
    if not ok:
        raise AmapWebError(429, "今日高德配额已用尽，请明天再试")


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    retry: bool,
) -> dict[str, Any]:
    """带单次重试的 GET 请求，每次真实调用都计入日配额。"""
    attempts = 2 if retry else 1
    for attempt in range(attempts):
        await _consume_daily_quota()
        try:
            resp = await client.get(url, params=params, timeout=10.0)
        except httpx.HTTPError as exc:
            if attempt < attempts - 1:
                await asyncio.sleep(_RETRY_DELAY)
                continue
            raise AmapWebError(502, f"高德服务连接失败: {exc}")
        if resp.status_code == 200:
            return resp.json()
        # 5xx（高德服务端错误）重试 1 次；4xx（配额/鉴权/参数错误）不重试
        if resp.status_code >= 500 and attempt < attempts - 1:
            await asyncio.sleep(_RETRY_DELAY)
            continue
        raise _map_http_error(resp.status_code, resp.text)
    raise AmapWebError(502, "高德服务重试后仍失败")


def _map_http_error(status_code: int, body: str) -> AmapWebError:
    message = body[:300] or "高德服务返回错误"
    if status_code == 429:
        return AmapWebError(429, "今日高德配额已用尽，请明天再试")
    return AmapWebError(502, f"高德服务返回 {status_code}: {message}")


async def geocode(address: str, city: str | None = None) -> dict[str, Any]:
    """地理编码。返回 { lng, lat, level, formatted_address }。

    - 白名单 level 之外 → 400"地址过于模糊"
    - 无法解析 → 400"地址无法解析"
    - 高德瞬时错误重试 1 次（0.2s），重试请求计入日配额
    """
    params: dict[str, Any] = {
        "key": settings.AMAP_WEB_API_KEY,
        "address": address,
        "output": "JSON",
    }
    if city:
        params["city"] = city

    async with httpx.AsyncClient(timeout=10.0) as client:
        data = await _get_json(client, _GEOCODE_URL, params, retry=True)

    if data.get("status") != "1" or not data.get("geocodes"):
        raise AmapWebError(400, "门店地址无法解析，请检查地址")
    geo = data["geocodes"][0]
    level = str(geo.get("level") or "")
    if level not in _GEOCODE_LEVEL_ALLOWED:
        raise AmapWebError(400, "门店地址过于模糊，请补充门牌号或详细地址")
    location = str(geo.get("location") or "")
    try:
        lng_str, lat_str = location.split(",")
        lng, lat = float(lng_str), float(lat_str)
    except (ValueError, TypeError):
        raise AmapWebError(400, "门店地址无法解析，请检查地址")
    return {
        "lng": lng,
        "lat": lat,
        "level": level,
        "formatted_address": str(geo.get("formatted_address") or ""),
    }


async def place_around(
    lng: float,
    lat: float,
    radius: int = 3000,
    types: str = _TYPES_FOOD,
    max_pages: int = _MAX_PAGES,
) -> list[dict[str, Any]]:
    """周边搜索，分页早停：空页或不足 25 条提前终止。单页瞬时错误重试 1 次。"""
    pois: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {
                "key": settings.AMAP_WEB_API_KEY,
                "location": f"{lng},{lat}",
                "radius": radius,
                "types": types,
                "offset": _PAGE_SIZE,
                "page": page,
                "output": "JSON",
            }
            data = await _get_json(client, _AROUND_URL, params, retry=True)
            if data.get("status") != "1":
                raise AmapWebError(
                    502, f"高德周边搜索失败: {data.get('info') or data.get('infocode') or ''}"
                )
            batch = data.get("pois") or []
            pois.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
    return pois


async def proxy_security_config() -> httpx.Response:
    """高德 JS API 安全密钥代理：前端不暴露 securityJsCode。

    前端设置 _AMapSecurityConfig.serviceHost 指向本服务，请求转发到
    https://restapi.amap.com/securityConfig 并附带 key + jscode。
    """
    params = {
        "key": settings.AMAP_JS_KEY,
        "jscode": settings.AMAP_SECURITY_JS_CODE,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.get(_SECURITY_CONFIG_URL, params=params)

