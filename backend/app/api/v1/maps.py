"""高德地图 MCP 接入 API — 工具列举 / 通用调用 / 常用便捷查询。

鉴权：所有端点校验 JWT（get_current_user）。
配置：backend/.env 中 AMAP_MAPS_API_KEY / AMAP_MCP_URL / AMAP_MCP_AUTH_TOKEN。
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_current_user
from app.services.amap_mcp import AmapMCPError, AmapMCPClient, amap_mcp_client

router = APIRouter(tags=["maps"])


def _http_error(exc: AmapMCPError) -> HTTPException:
    """将 MCP 异常映射为 HTTP 状态码。"""
    if "未配置" in str(exc):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


async def _with_client() -> AmapMCPClient:
    return amap_mcp_client


@router.get("/maps/tools")
async def list_maps_tools(
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """列出高德 MCP 当前暴露的全部工具（name/description/inputSchema）。"""
    try:
        return {"tools": await client.list_tools()}
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.post("/maps/invoke")
async def invoke_maps_tool(
    body: dict[str, Any],
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """通用工具调用。请求体：{"tool": "maps_weather", "arguments": {"city": "北京"}}"""
    tool = body.get("tool")
    if not isinstance(tool, str) or not tool:
        raise HTTPException(status_code=422, detail="缺少工具名 tool")
    arguments = body.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="arguments 必须是对象")
    try:
        return await client.call_tool(tool, arguments)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/geocode")
async def maps_geocode(
    address: str = Query(..., min_length=1, max_length=200),
    city: str | None = Query(None, max_length=50),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """地理编码：结构化地址 -> 经纬度。"""
    try:
        return await client.geocode(address, city)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/regeocode")
async def maps_regeocode(
    location: str = Query(..., min_length=1, max_length=100),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """逆地理编码：经纬度（经度,纬度）-> 行政区划地址。"""
    try:
        return await client.regeocode(location)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/ip-location")
async def maps_ip_location(
    ip: str = Query(..., min_length=1, max_length=50),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """IP 定位。"""
    try:
        return await client.ip_location(ip)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/weather")
async def maps_weather(
    city: str = Query(..., min_length=1, max_length=50),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """天气查询：城市名称或 adcode。"""
    try:
        return await client.weather(city)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/distance")
async def maps_distance(
    origins: str = Query(..., min_length=1, max_length=500),
    destination: str = Query(..., min_length=1, max_length=100),
    measure_type: Literal["0", "1", "3"] | None = Query(None, alias="type"),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """距离测量。origins 可多个坐标以分号分隔；type: 0 直线 / 1 驾车 / 3 步行。"""
    try:
        return await client.distance(origins, destination, measure_type)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/poi")
async def maps_poi_search(
    keywords: str = Query(..., min_length=1, max_length=100),
    city: str | None = Query(None, max_length=50),
    types: str | None = Query(None, max_length=100),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """关键词搜索 POI（竞品/商圈/门店检索）。"""
    try:
        return await client.poi_search(keywords, city, types)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/around")
async def maps_around_search(
    location: str = Query(..., min_length=1, max_length=100),
    keywords: str | None = Query(None, max_length=100),
    radius: str | None = Query(None, max_length=20),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """周边搜索：以 location（经度,纬度）为中心，搜索半径内 POI。"""
    try:
        return await client.around_search(location, keywords, radius)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/poi/{poi_id}")
async def maps_poi_detail(
    poi_id: str,
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """查询 POI ID 的详细信息。"""
    try:
        return await client.search_detail(poi_id)
    except AmapMCPError as exc:
        raise _http_error(exc)


@router.get("/maps/route")
async def maps_route(
    origin: str = Query(..., min_length=1, max_length=100),
    destination: str = Query(..., min_length=1, max_length=100),
    mode: Literal["driving", "walking", "bicycling", "transit"] = "driving",
    city: str | None = Query(None, max_length=50, description="公交规划起点城市"),
    cityd: str | None = Query(None, max_length=50, description="公交规划终点城市"),
    client: AmapMCPClient = Depends(_with_client),
    _user: Any = Depends(get_current_user),
):
    """路径规划。mode: driving/walking/bicycling/transit。"""
    try:
        return await client.route(origin, destination, mode, city, cityd)
    except AmapMCPError as exc:
        raise _http_error(exc)
