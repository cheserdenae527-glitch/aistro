# -*- coding: utf-8 -*-
"""高德地图 MCP 客户端服务。

通过 MCP 协议连接高德地图 MCP Server（支持两种接入方式）：
1. 高德官方 Streamable HTTP：https://mcp.amap.com/mcp?key=<AMAP_MAPS_API_KEY>
2. ModelScope MCP 广场生成的 SSE 地址：https://mcp.api-inference.modelscope.net/<id>/sse

配置项（backend/.env）：
    AMAP_MAPS_API_KEY  高德开放平台 Web 服务 Key
    AMAP_MCP_URL       MCP 地址，留空默认官方 Streamable HTTP
    AMAP_MCP_AUTH_TOKEN 可选，ModelScope 代理鉴权 Token

工具列表（高德官方 MCP，线上实际 15 个）：
    maps_geo / maps_regeocode / maps_ip_location / maps_weather
    maps_direction_driving / maps_direction_walking / maps_direction_bicycling
    maps_direction_transit_integrated / maps_distance
    maps_text_search / maps_around_search / maps_search_detail
    maps_schema_personal_map / maps_schema_navi / maps_schema_take_taxi
"""
from __future__ import annotations

import json
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from app.core.config import settings

# 高德官方 MCP Streamable HTTP 地址模板
_OFFICIAL_MCP_URL = "https://mcp.amap.com/mcp"


class AmapMCPError(Exception):
    """Amap MCP 调用失败。"""


class AmapMCPClient:
    """连接高德 MCP Server，提供工具列举与调用能力。"""

    def __init__(
        self,
        api_key: str | None = None,
        url: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.AMAP_MAPS_API_KEY) or ""
        self.url = (url if url is not None else settings.AMAP_MCP_URL) or ""
        self.auth_token = (
            auth_token if auth_token is not None else settings.AMAP_MCP_AUTH_TOKEN
        ) or ""

    # ----------------------------------------------------------
    # 连接信息
    # ----------------------------------------------------------

    def endpoint_url(self) -> str:
        """返回实际连接的 MCP 地址。"""
        if self.url:
            return self.url
        if not self.api_key:
            raise AmapMCPError(
                "未配置高德 MCP：请在 backend/.env 设置 AMAP_MAPS_API_KEY"
                "（或 AMAP_MCP_URL 指向 ModelScope 生成的 SSE 地址）"
            )
        return f"{_OFFICIAL_MCP_URL}?key={self.api_key}"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _is_sse(self, url: str) -> bool:
        return "/sse" in url.lower()

    # ----------------------------------------------------------
    # 会话
    # ----------------------------------------------------------

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        """建立一次 MCP 会话（自动选择 SSE / Streamable HTTP）。"""
        url = self.endpoint_url()
        headers = self._headers()
        stack = AsyncExitStack()
        try:
            if self._is_sse(url):
                read, write, _ = await stack.enter_async_context(
                    sse_client(url, headers=headers)
                )
            else:
                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(url, headers=headers)
                )
            session = ClientSession(read, write)
            await stack.enter_async_context(session)
            await session.initialize()
            yield session
        except Exception as exc:
            # 连接/初始化阶段失败：给出可读错误
            if isinstance(exc, AmapMCPError):
                raise
            raise AmapMCPError(f"连接高德 MCP 失败：{exc}") from exc
        finally:
            await stack.aclose()

    # ----------------------------------------------------------
    # 工具列举 / 通用调用
    # ----------------------------------------------------------

    async def list_tools(self) -> list[dict[str, Any]]:
        """返回 MCP Server 暴露的全部工具（name/description/inputSchema）。"""
        async with self._session() as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """调用指定 MCP 工具，返回解析后的结果。"""
        if not name:
            raise AmapMCPError("缺少工具名 tool")
        async with self._session() as session:
            result: CallToolResult = await session.call_tool(name, arguments or {})
        return self._parse_result(result, name)

    @staticmethod
    def _parse_result(result: CallToolResult, name: str) -> dict[str, Any]:
        """将 MCP 工具结果整理为统一结构。"""
        if result.isError:
            raise AmapMCPError(f"工具 {name} 执行失败：{_content_to_text(result.content)}")

        # 优先结构化内容
        if getattr(result, "structuredContent", None) is not None:
            return {"tool": name, "data": result.structuredContent}

        text = _content_to_text(result.content)
        try:
            data = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            data = {"raw": text}
        return {"tool": name, "data": data}

    # ----------------------------------------------------------
    # 常用工具便捷方法（餐饮运营常用场景）
    # ----------------------------------------------------------

    async def geocode(self, address: str, city: str | None = None) -> dict[str, Any]:
        """地理编码：结构化地址 -> 经纬度。"""
        args: dict[str, Any] = {"address": address}
        if city:
            args["city"] = city
        return await self.call_tool("maps_geo", args)

    async def regeocode(self, location: str) -> dict[str, Any]:
        """逆地理编码：经纬度 -> 行政区划地址。location 格式：经度,纬度"""
        return await self.call_tool("maps_regeocode", {"location": location})

    async def ip_location(self, ip: str) -> dict[str, Any]:
        """IP 定位。"""
        return await self.call_tool("maps_ip_location", {"ip": ip})

    async def weather(self, city: str) -> dict[str, Any]:
        """天气查询：城市名称或 adcode。"""
        return await self.call_tool("maps_weather", {"city": city})

    async def distance(
        self,
        origins: str,
        destination: str,
        measure_type: str | None = None,
    ) -> dict[str, Any]:
        """距离测量。origins 支持多个坐标用分号分隔；type: 0 直线 / 1 驾车 / 3 步行。"""
        args: dict[str, Any] = {"origins": origins, "destination": destination}
        if measure_type:
            args["type"] = measure_type
        return await self.call_tool("maps_distance", args)

    async def poi_search(
        self,
        keywords: str,
        city: str | None = None,
        types: str | None = None,
    ) -> dict[str, Any]:
        """关键词搜索 POI（竞品/商圈/门店检索）。"""
        args: dict[str, Any] = {"keywords": keywords}
        if city:
            args["city"] = city
        if types:
            args["types"] = types
        return await self.call_tool("maps_text_search", args)

    async def around_search(
        self,
        location: str,
        keywords: str | None = None,
        radius: str | None = None,
    ) -> dict[str, Any]:
        """周边搜索：以 location（经度,纬度）为中心搜索半径内 POI。"""
        args: dict[str, Any] = {"location": location}
        if keywords:
            args["keywords"] = keywords
        if radius:
            args["radius"] = radius
        return await self.call_tool("maps_around_search", args)

    async def search_detail(self, poi_id: str) -> dict[str, Any]:
        """查询 POI ID 的详细信息。"""
        return await self.call_tool("maps_search_detail", {"id": poi_id})

    async def route(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        city: str | None = None,
        cityd: str | None = None,
    ) -> dict[str, Any]:
        """路径规划。mode: driving 驾车 / walking 步行 / bicycling 骑行 / transit 公交。"""
        tool_map = {
            "driving": "maps_direction_driving",
            "walking": "maps_direction_walking",
            "bicycling": "maps_direction_bicycling",
            "transit": "maps_direction_transit_integrated",
        }
        tool = tool_map.get(mode)
        if not tool:
            raise AmapMCPError(
                f"不支持的出行方式：{mode}（可选 driving/walking/bicycling/transit）"
            )
        args: dict[str, Any] = {"origin": origin, "destination": destination}
        if mode == "transit":
            if not city or not cityd:
                raise AmapMCPError(
                    "公交路径规划需要同时提供 city（起点城市）与 cityd（终点城市）"
                )
            args["city"] = city
            args["cityd"] = cityd
        return await self.call_tool(tool, args)


def _content_to_text(content: Any) -> str:
    """提取 MCP 工具返回的文本内容。"""
    parts: list[str] = []
    for block in content or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


# 模块级单例，供 API 层复用
amap_mcp_client = AmapMCPClient()
