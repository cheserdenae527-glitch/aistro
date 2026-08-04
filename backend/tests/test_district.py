"""商圈分析 K1 测试 — mock 高德，覆盖 SPEC-DISTRICT v0.5。

运行：cd D:\two\backend && pytest tests/test_district.py -v
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from app.services.amap_web import AmapWebError, _get_json, daily_quota_key, geocode
from app.services.district import (
    compute_stats,
    is_self_poi,
    is_similar_name,
    map_competitor_types,
    parse_poi,
)


# ============================================================
# Helpers
# ============================================================

def auth_headers(client) -> dict:
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com", "password": "admin123",
    })
    if resp.status_code != 200:
        client.post("/api/v1/auth/register", json={
            "email": "admin@test.com", "password": "admin123", "name": "Test Admin",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "admin123",
        })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def create_shop(
    client,
    name: str = "蜀味火锅总店",
    category: str = "火锅",
    address: str = "成都市锦江区春熙路8号",
) -> str:
    m = client.post("/api/v1/merchants", json={"name": "测试商家"}, headers=auth_headers(client))
    mid = m.json()["id"]
    s = client.post(
        f"/api/v1/merchants/{mid}/shops",
        json={"name": name, "category": category, "address": address},
        headers=auth_headers(client),
    )
    return s.json()["id"]


def _geocode_ok(lng=104.081, lat=30.655):
    async def _f(address, city=None):
        return {"lng": lng, "lat": lat, "level": "门牌号", "formatted_address": address}
    return _f


# ============================================================
# 鉴权
# ============================================================

def test_anonymous_401(client):
    resp = client.post(f"/api/v1/shops/{uuid.uuid4()}/district/analyze")
    assert resp.status_code == 401


def test_cross_user_404(client):
    resp = client.get(
        f"/api/v1/shops/{uuid.uuid4()}/district/latest",
        headers=auth_headers(client),
    )
    assert resp.status_code == 404


# ============================================================
# 业务逻辑单测
# ============================================================

def test_is_similar_name_short_name_not_compared():
    assert is_similar_name("茶", "茶餐厅") is False
    assert is_similar_name("蜀味火锅总店", "蜀味火锅总店") is True
    assert is_similar_name("海底捞春熙路店", "海底捞玉林店") is False


def test_is_self_poi_distance_threshold():
    assert is_self_poi("蜀味火锅总店", "蜀味火锅总店", 5) is True
    assert is_self_poi("蜀味火锅总店", "蜀味火锅总店", 10) is False  # >=10 不排除
    assert is_self_poi("海底捞春熙路店", "海底捞玉林店", 5) is False


def test_map_competitor_types_full_and_none():
    ok, types = map_competitor_types("火锅")
    assert ok is True
    assert "火锅店" in types
    ok_none, types_none = map_competitor_types("")
    assert ok_none is False and types_none == ()
    ok_none2, _ = map_competitor_types("未知品类")
    assert ok_none2 is False


def test_compute_stats_excludes_self_and_density():
    pois = [
        {"category": "火锅店", "is_competitor": True, "excluded_as_self": False},
        {"category": "咖啡厅", "is_competitor": False, "excluded_as_self": False},
        {"category": "火锅店", "is_competitor": False, "excluded_as_self": True},
    ]
    stats = compute_stats(pois, 3000)
    assert stats["poi_total"] == 2
    assert stats["competitor_count"] == 1
    assert stats["excluded_self_count"] == 1
    assert stats["density_per_km2"] == pytest.approx(2 / (3.141592653589793 * 9), abs=0.01)


def test_parse_poi_marks_self_and_competitor():
    shop_name = "蜀味火锅总店"
    ok, comp_types = map_competitor_types("火锅")
    assert ok
    poi = {
        "id": "p1", "name": "蜀味火锅总店", "type": "餐饮服务;中餐厅;火锅店",
        "address": "春熙路8号", "location": "104.081,30.655", "distance": "5",
    }
    item = parse_poi(poi, shop_name, comp_types)
    assert item["excluded_as_self"] is True
    assert item["is_competitor"] is False

    poi2 = {
        "id": "p2", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
        "location": "104.091,30.655", "distance": "300",
    }
    item2 = parse_poi(poi2, shop_name, comp_types)
    assert item2["excluded_as_self"] is False
    assert item2["is_competitor"] is True


# ============================================================
# 高德调用重试 / 配额 / 早停
# ============================================================

class FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self._text = text

    def json(self):
        return {"status": "1", "geocodes": []}

    @property
    def text(self):
        return self._text


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def get(self, url, params=None, timeout=None):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


def test_get_json_retries_on_502(monkeypatch):
    async def _no_quota():
        return None
    monkeypatch.setattr("app.services.amap_web._consume_daily_quota", _no_quota)
    client = FakeClient([FakeResp(502, "bad gateway"), FakeResp(200)])
    result = None
    import asyncio
    async def run():
        nonlocal result
        result = await _get_json(client, "http://x", {}, retry=True)
    asyncio.run(run())
    assert client.calls == 2
    assert result == {"status": "1", "geocodes": []}


def test_get_json_does_not_retry_429(monkeypatch):
    async def _no_quota():
        return None
    monkeypatch.setattr("app.services.amap_web._consume_daily_quota", _no_quota)
    client = FakeClient([FakeResp(429, "quota"), FakeResp(200)])
    with pytest.raises(AmapWebError) as exc:
        import asyncio
        asyncio.run(_get_json(client, "http://x", {}, retry=True))
    assert exc.value.status_code == 429
    assert client.calls == 1


def test_daily_quota_key_uses_shanghai_date():
    key = daily_quota_key()
    assert key.startswith("amap_daily_quota:")
    assert len(key) == len("amap_daily_quota:") + 10


# ============================================================
# analyze 成功 / 失败路径
# ============================================================

def test_analyze_missing_address_400_no_snapshot(client):
    shop_id = create_shop(client, address="")
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    assert resp.status_code == 400
    snap = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots", headers=auth_headers(client)
    )
    assert snap.json()["total"] == 0


def test_analyze_geocode_failure_400_no_snapshot(client, monkeypatch):
    shop_id = create_shop(client)

    async def _bad_geocode(address, city=None):
        raise AmapWebError(400, "门店地址无法解析，请检查地址")

    monkeypatch.setattr("app.api.v1.district.geocode", _bad_geocode)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    assert resp.status_code == 400
    snap = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots", headers=auth_headers(client)
    )
    assert snap.json()["total"] == 0


def test_analyze_success_with_self_exclusion_and_competitor(client, monkeypatch):
    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())

    async def _around(lng, lat, radius=3000, types="050000", max_pages=4):
        return [
            {"id": "self1", "name": "蜀味火锅总店", "type": "餐饮服务;中餐厅;火锅店",
             "address": "春熙路8号", "location": "104.081,30.655", "distance": "5"},
            {"id": "c1", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
             "address": "春熙路100号", "location": "104.091,30.655", "distance": "300"},
            {"id": "c2", "name": "咖啡小馆", "type": "餐饮服务;咖啡厅",
             "location": "104.071,30.655", "distance": "200"},
        ]

    monkeypatch.setattr("app.api.v1.district.place_around", _around)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["poi_total"] == 2
    assert body["competitor_count"] == 1
    assert body["excluded_self_count"] == 1
    assert body["mapping_status"] == "full"

    snap = client.get(
        f"/api/v1/shops/{shop_id}/district/latest", headers=auth_headers(client)
    )
    assert snap.json()["poi_total"] == 2
    assert snap.json()["density_per_km2"] > 0


def test_analyze_search_failure_creates_failed_snapshot(client, monkeypatch):
    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())

    async def _fail(lng, lat, radius=3000, types="050000", max_pages=4):
        raise AmapWebError(502, "高德服务重试后仍失败")

    monkeypatch.setattr("app.api.v1.district.place_around", _fail)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    assert resp.status_code == 502
    failed = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots?status=failed",
        headers=auth_headers(client),
    )
    assert failed.json()["total"] == 1
    assert failed.json()["items"][0]["error_message"]


def test_analyze_quota_429_no_snapshot(client, monkeypatch):
    shop_id = create_shop(client)

    async def _quota(address, city=None):
        raise AmapWebError(429, "今日高德配额已用尽，请明天再试")

    monkeypatch.setattr("app.api.v1.district.geocode", _quota)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    assert resp.status_code == 429
    snap = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots", headers=auth_headers(client)
    )
    assert snap.json()["total"] == 0


# ============================================================
# 快照列表 / 详情 / 竞品
# ============================================================

def test_snapshot_list_status_filter_and_pagination(client, monkeypatch):
    async def _peek(key): return True
    async def _set(key, ttl=60): return None
    monkeypatch.setattr("app.api.v1.district.peek_rate_limit", _peek)
    monkeypatch.setattr("app.api.v1.district.set_rate_limit", _set)
    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())
    async def _empty_around(lng, lat, radius=3000, types="050000", max_pages=4):
        return []

    monkeypatch.setattr("app.api.v1.district.place_around", _empty_around)
    # 连续两次成功分析 → 2 条 analyzed
    for _ in range(2):
        resp = client.post(
            f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
        )
        assert resp.status_code == 200
    listed = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots?status=analyzed&page=1&size=1",
        headers=auth_headers(client),
    ).json()
    assert listed["total"] == 2
    assert len(listed["items"]) == 1  # size=1


def test_competitors_endpoint(client, monkeypatch):
    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())

    async def _around(lng, lat, radius=3000, types="050000", max_pages=4):
        return [
            {"id": "c1", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
             "location": "104.091,30.655", "distance": "300"},
        ]

    monkeypatch.setattr("app.api.v1.district.place_around", _around)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    snap_id = resp.json()["snapshot_id"]
    comp = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots/{snap_id}/competitors",
        headers=auth_headers(client),
    )
    assert comp.status_code == 200
    assert len(comp.json()) == 1
    assert comp.json()[0]["name"] == "隔壁火锅"


# ============================================================
# map-config
# ============================================================

def test_map_config_503_without_key(client):
    resp = client.get("/api/v1/district/map-config", headers=auth_headers(client))
    assert resp.status_code == 503


def test_map_config_returns_key(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AMAP_JS_KEY", "js-test-key")
    resp = client.get("/api/v1/district/map-config", headers=auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["amap_js_key"] == "js-test-key"
