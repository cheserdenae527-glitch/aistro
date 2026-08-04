"""高德地图 MCP 接入测试 — 覆盖路由鉴权、工具列举/调用、便捷端点与服务层。

运行方式：
    cd D:\two\backend
    pytest tests/test_amap_mcp.py -v

需要数据库 + Redis 运行中（docker compose up -d）。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.amap_mcp import AmapMCPError, AmapMCPClient, amap_mcp_client


def auth_headers(client) -> dict:
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    if resp.status_code != 200:
        client.post("/api/v1/auth/register", json={
            "email": "admin@test.com",
            "password": "admin123",
            "name": "Test Admin",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com",
            "password": "admin123",
        })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ============================================================
# 服务层单测（不依赖网络）
# ============================================================

def test_endpoint_url_uses_configured_url():
    client = AmapMCPClient(api_key="", url="https://mcp.api-inference.modelscope.net/abc/sse")
    assert client.endpoint_url() == "https://mcp.api-inference.modelscope.net/abc/sse"


def test_endpoint_url_defaults_to_official_with_key():
    client = AmapMCPClient(api_key="my-key", url="")
    assert client.endpoint_url() == "https://mcp.amap.com/mcp?key=my-key"


def test_endpoint_url_raises_when_unconfigured():
    client = AmapMCPClient(api_key="", url="")
    with pytest.raises(AmapMCPError):
        client.endpoint_url()


def test_parse_result_text_json():
    class _Block:
        text = '{"city": "北京市"}'

    class _Result:
        isError = False
        structuredContent = None
        content = [_Block()]

    out = AmapMCPClient._parse_result(_Result(), "maps_weather")
    assert out == {"tool": "maps_weather", "data": {"city": "北京市"}}


def test_parse_result_error():
    class _Block:
        text = "QUOTA_EXHAUSTED"

    class _Result:
        isError = True
        structuredContent = None
        content = [_Block()]

    with pytest.raises(AmapMCPError):
        AmapMCPClient._parse_result(_Result(), "maps_weather")


def test_route_invalid_mode():
    client = AmapMCPClient(api_key="k")
    with pytest.raises(AmapMCPError):
        # 直接调用内部参数校验（不触发网络）
        import asyncio
        asyncio.run(client.route("116,39", "117,40", mode="fly"))


# ============================================================
# API 层测试（mock 掉 MCP 客户端，避免真实网络请求）
# ============================================================

@pytest.fixture(autouse=True)
def _mock_amap_client(monkeypatch):
    """把所有 MCP 客户端方法替换为 AsyncMock，防止测试触发真实网络。"""
    for name in ("list_tools", "call_tool", "geocode", "regeocode",
                 "ip_location", "weather", "distance", "poi_search",
                 "around_search", "search_detail", "route"):
        monkeypatch.setattr(amap_mcp_client, name, AsyncMock())
    yield


def test_maps_requires_auth(client):
    resp = client.get("/api/v1/maps/tools")
    assert resp.status_code == 401


def test_maps_tools(client):
    amap_mcp_client.list_tools.return_value = [
        {"name": "maps_weather", "description": "天气查询", "inputSchema": {}}
    ]
    resp = client.get("/api/v1/maps/tools", headers=auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["tools"][0]["name"] == "maps_weather"


def test_maps_invoke(client):
    amap_mcp_client.call_tool.return_value = {
        "tool": "maps_weather",
        "data": {"city": "北京市"},
    }
    resp = client.post(
        "/api/v1/maps/invoke",
        json={"tool": "maps_weather", "arguments": {"city": "北京"}},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "北京市"
    amap_mcp_client.call_tool.assert_awaited_once_with(
        "maps_weather", {"city": "北京"}
    )


def test_maps_invoke_missing_tool(client):
    resp = client.post(
        "/api/v1/maps/invoke",
        json={"arguments": {"city": "北京"}},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_maps_weather_endpoint(client):
    amap_mcp_client.weather.return_value = {
        "tool": "maps_weather",
        "data": {"city": "北京市"},
    }
    resp = client.get(
        "/api/v1/maps/weather?city=%E5%8C%97%E4%BA%AC",
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    amap_mcp_client.weather.assert_awaited_once_with("北京")


def test_maps_unconfigured_returns_503(client, monkeypatch):
    def _raise():
        raise AmapMCPError("未配置高德 MCP：请在 backend/.env 设置 AMAP_MAPS_API_KEY")

    monkeypatch.setattr(amap_mcp_client, "list_tools", AsyncMock(side_effect=_raise))
    resp = client.get("/api/v1/maps/tools", headers=auth_headers(client))
    assert resp.status_code == 503
    assert "未配置" in resp.json()["detail"]


def test_maps_upstream_error_returns_502(client, monkeypatch):
    async def _boom(tool, arguments):
        raise AmapMCPError("工具 maps_weather 执行失败：QUOTA_EXHAUSTED")

    monkeypatch.setattr(amap_mcp_client, "call_tool", _boom)
    resp = client.post(
        "/api/v1/maps/invoke",
        json={"tool": "maps_weather", "arguments": {"city": "北京"}},
        headers=auth_headers(client),
    )
    assert resp.status_code == 502
