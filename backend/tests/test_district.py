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
    is_competitor_poi,
    is_self_poi,
    is_similar_name,
    map_competitor_types,
    merge_competitor_detail,
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
    ok, mapping = map_competitor_types("火锅")
    assert ok is True
    assert "火锅店" in mapping["type_keywords"]
    assert "050117" in mapping["typecodes"]
    ok_none, mapping_none = map_competitor_types("")
    assert ok_none is False and mapping_none == {}
    ok_none2, _ = map_competitor_types("未知品类")
    assert ok_none2 is False


def test_is_competitor_poi_type_keyword_and_typecode():
    mapping = {
        "type_keywords": ("快餐厅", "小吃快餐店"),
        "typecodes": ("050300", "050301", "050302", "050303"),
    }
    # type 文本子串命中
    assert is_competitor_poi("餐饮服务;快餐厅;快餐厅", "", mapping) is True
    # type 不含关键词，但 typecode 精确命中（麦当劳 = 050302）
    assert is_competitor_poi("餐饮服务;餐饮相关场所;餐饮相关", "050302", mapping) is True
    # 多值 typecode（| 分隔）命中其一
    assert is_competitor_poi("餐饮服务;餐饮相关场所;餐饮相关", "050302|050900", mapping) is True
    # typecode 未命中（中餐厅 050100）→ 非竞品
    assert is_competitor_poi("餐饮服务;中餐厅;中餐厅", "050100", mapping) is False
    # 空映射 → 非竞品
    assert is_competitor_poi("餐饮服务;快餐厅;快餐厅", "050300", {}) is False
    # 空白 typecode / 无关键词 → 非竞品
    assert is_competitor_poi("餐饮服务;中餐厅;中餐厅", "", mapping) is False
    # 050112 实测为湖北菜(鄂菜)，不在快餐映射内 → 非竞品（防回归）
    assert is_competitor_poi("餐饮服务;中餐厅;湖北菜(鄂菜)", "050112", mapping) is False


def test_map_competitor_types_normalizes_aliases():
    """常见自由文本品类应归一为规范 key；无法归一的保持 none。"""
    assert map_competitor_types("火锅店")[0] is True
    assert map_competitor_types("火锅店")[1]["typecodes"] == ("050117",)
    assert map_competitor_types(" 快餐店 ")[0] is True
    assert map_competitor_types("咖啡厅")[1]["typecodes"] == ("050500",)
    assert map_competitor_types("甜品店")[0] is True
    assert map_competitor_types("日本料理")[0] is True
    assert map_competitor_types("私房菜")[0] is True
    assert map_competitor_types("私房菜")[1]["typecodes"] == ("050118",)
    # 无干净对应类 → none（不硬映射）
    assert map_competitor_types("饮品") == (False, {})


def test_private_kitchen_category_maps_to_050118():
    """私房菜为正式品类，映射 050118（特色/地方风味餐厅，与烧烤同码，文档已标注取舍）。"""
    ok, mapping = map_competitor_types("私房菜")
    assert ok
    assert "私房菜" in mapping["type_keywords"]
    assert mapping["typecodes"] == ("050118",)
    # 别名归一
    ok2, mapping2 = map_competitor_types("私房菜馆")
    assert ok2 and mapping2 == mapping


def test_fast_food_typecodes_exclude_050112():
    """2026 实测高德对湖北菜馆(鄂菜)也发 050112，纳入会误伤，必须排除。"""
    ok, mapping = map_competitor_types("快餐")
    assert ok
    assert "050112" not in mapping["typecodes"]


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
    ok, comp_mapping = map_competitor_types("火锅")
    assert ok
    poi = {
        "id": "p1", "name": "蜀味火锅总店", "type": "餐饮服务;中餐厅;火锅店",
        "typecode": "050117", "address": "春熙路8号",
        "location": "104.081,30.655", "distance": "5",
    }
    item = parse_poi(poi, shop_name, comp_mapping)
    assert item["excluded_as_self"] is True
    assert item["is_competitor"] is False

    poi2 = {
        "id": "p2", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
        "typecode": "050117", "location": "104.091,30.655", "distance": "300",
    }
    item2 = parse_poi(poi2, shop_name, comp_mapping)
    assert item2["excluded_as_self"] is False
    assert item2["is_competitor"] is True
    assert item2["is_competitor_auto"] is True
    assert item2["is_competitor_manual"] is False
    # 周边搜索 extensions=all 带回的基础字段
    assert item2["typecode"] == "050117"
    assert item2["tel"] is None
    assert item2["tag"] is None


def test_merge_competitor_detail_merges_amap_fields():
    item = {"poi_id": "p1", "name": "隔壁火锅", "is_competitor": True,
            "typecode": "050117", "tel": None, "tag": None}
    detail = {
        "typecode": "050117", "tel": "028-12345678", "tag": "火锅",
        "business_area": "春熙路", "rating": 4.5, "cost": 88.0,
        "business_hours": "周一至周日 11:00-22:00",
    }
    merged = merge_competitor_detail(item, detail)
    assert merged["rating"] == 4.5
    assert merged["cost"] == 88.0
    assert merged["business_hours"].startswith("周一至周日")
    assert merged["business_area"] == "春熙路"
    assert merged["tel"] == "028-12345678"
    # detail 为空/缺失字段时不覆盖（保留已有值）
    merged2 = merge_competitor_detail(item, None)
    assert merged2 == item
    merged3 = merge_competitor_detail(
        {"poi_id": "p2", "name": "x", "is_competitor": True},
        {"rating": None, "cost": "", "business_hours": ""},
    )
    assert merged3.get("rating") is None
    assert merged3.get("cost") is None


def test_parse_poi_typecode_fallback_when_type_text_is_generic():
    """type 文本不含关键词但 typecode 精确命中 → 仍判竞品（高德数据常见形态）。"""
    shop_name = "蜀味火锅总店"
    _, comp_mapping = map_competitor_types("火锅")
    poi = {
        "id": "p3", "name": "某火锅店", "type": "餐饮服务;餐饮相关场所;餐饮相关",
        "typecode": "050117", "location": "104.091,30.655", "distance": "300",
    }
    item = parse_poi(poi, shop_name, comp_mapping)
    assert item["excluded_as_self"] is False
    assert item["is_competitor"] is True

    # 中餐厅(050100) 不属火锅竞品
    poi_not = {
        "id": "p4", "name": "川菜馆", "type": "餐饮服务;中餐厅;四川菜(川菜)",
        "typecode": "050102", "location": "104.091,30.655", "distance": "300",
    }
    item_not = parse_poi(poi_not, shop_name, comp_mapping)
    assert item_not["is_competitor"] is False


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


def test_geocode_whitelist_accepts_menzhi(monkeypatch):
    """高德对门牌地址返回 level=门址，必须放行（历史上误判为模糊）。"""
    async def _fake_get_json(client, url, params, retry):
        return {"status": "1", "geocodes": [{"level": "门址", "location": "114.2999,30.5814", "formatted_address": "武汉市江岸区沿江大道144号"}]}
    monkeypatch.setattr("app.services.amap_web._get_json", _fake_get_json)
    import asyncio
    result = asyncio.run(geocode("武汉市江岸区沿江大道144号"))
    assert result["level"] == "门址"
    assert result["lng"] == pytest.approx(114.2999)


def test_geocode_whitelist_rejects_vague_level(monkeypatch):
    """住宅区/区县等模糊级别仍应拒绝（400，不建记录）。"""
    async def _fake_get_json(client, url, params, retry):
        return {"status": "1", "geocodes": [{"level": "住宅区", "location": "114.2978,30.5796", "formatted_address": "武汉江滩"}]}
    monkeypatch.setattr("app.services.amap_web._get_json", _fake_get_json)
    import asyncio
    with pytest.raises(AmapWebError) as exc:
        asyncio.run(geocode("武汉江滩"))
    assert exc.value.status_code == 400
    assert "过于模糊" in exc.value.detail


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

    async def _detail(poi_id: str):
        return {"rating": 4.6, "cost": 88.0, "business_hours": "11:00-22:00",
                "business_area": "春熙路", "tel": "028-12345678", "typecode": "050117", "tag": "火锅"}

    monkeypatch.setattr("app.api.v1.district.place_detail", _detail)
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

    # 竞品深度数据落库：快照详情 POI 携带评分/人均/营业时间
    detail = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots/{body['snapshot_id']}",
        headers=auth_headers(client),
    ).json()
    comp = next(p for p in detail["pois"] if p["is_competitor"])
    assert comp["rating"] == 4.6
    assert comp["cost"] == 88.0
    assert comp["business_hours"] == "11:00-22:00"
    assert comp["business_area"] == "春熙路"
    assert comp["tel"] == "028-12345678"
    assert comp["typecode"] == "050117"


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


def test_poi_override_endpoints_set_and_revert(client, monkeypatch):
    """人工标记：设为竞品/非竞品 → 竞品列表联动；取消标记 → 还原自动判定。"""
    async def _peek(key): return True
    async def _set(key, ttl=60): return None
    monkeypatch.setattr("app.api.v1.district.peek_rate_limit", _peek)
    monkeypatch.setattr("app.api.v1.district.set_rate_limit", _set)

    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())

    async def _around(lng, lat, radius=3000, types="050000", max_pages=4):
        return [
            {"id": "c1", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
             "typecode": "050117", "location": "104.091,30.655", "distance": "300"},
            {"id": "c2", "name": "咖啡小馆", "type": "餐饮服务;咖啡厅;咖啡厅",
             "typecode": "050500", "location": "104.071,30.655", "distance": "200"},
        ]

    monkeypatch.setattr("app.api.v1.district.place_around", _around)
    async def _detail(poi_id: str):
        return {"rating": 4.5, "cost": 80.0, "typecode": "050117", "business_hours": "11:00-22:00"}
    monkeypatch.setattr("app.api.v1.district.place_detail", _detail)

    h = auth_headers(client)
    snap_id = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=h
    ).json()["snapshot_id"]

    def _comp_ids():
        r = client.get(
            f"/api/v1/shops/{shop_id}/district/snapshots/{snap_id}/competitors", headers=h
        )
        return {c["poi_id"] for c in r.json()}

    # 自动判定：只有火锅店是竞品
    assert _comp_ids() == {"c1"}

    # 手动把咖啡小馆(c2)设为竞品 → 进入竞品列表
    r = client.put(
        f"/api/v1/shops/{shop_id}/district/poi-overrides/c2", headers=h,
        json={"is_competitor": True},
    )
    assert r.status_code == 200
    assert _comp_ids() == {"c1", "c2"}

    # 手动把隔壁火锅(c1)设为非竞品 → 移出竞品列表
    r = client.put(
        f"/api/v1/shops/{shop_id}/district/poi-overrides/c1", headers=h,
        json={"is_competitor": False},
    )
    assert r.status_code == 200
    assert _comp_ids() == {"c2"}

    # 取消 c2 的手动标记 → 还原为自动判定（非竞品），只剩 c1（仍是手动非竞品）
    r = client.delete(
        f"/api/v1/shops/{shop_id}/district/poi-overrides/c2", headers=h
    )
    assert r.status_code == 204
    assert _comp_ids() == set()

    # 取消 c1 的手动标记 → 还原为自动判定（竞品）
    client.delete(f"/api/v1/shops/{shop_id}/district/poi-overrides/c1", headers=h)
    assert _comp_ids() == {"c1"}

    # 覆盖列表可查
    ov = client.get(
        f"/api/v1/shops/{shop_id}/district/poi-overrides", headers=h
    ).json()
    assert ov["total"] == 0


def test_analyze_applies_persisted_override(client, monkeypatch):
    """人工标记跨快照生效：重新分析后新快照沿用人工判定。"""
    async def _peek(key): return True
    async def _set(key, ttl=60): return None
    monkeypatch.setattr("app.api.v1.district.peek_rate_limit", _peek)
    monkeypatch.setattr("app.api.v1.district.set_rate_limit", _set)

    shop_id = create_shop(client)
    monkeypatch.setattr("app.api.v1.district.geocode", _geocode_ok())

    async def _around(lng, lat, radius=3000, types="050000", max_pages=4):
        return [
            {"id": "c1", "name": "隔壁火锅", "type": "餐饮服务;中餐厅;火锅店",
             "typecode": "050117", "location": "104.091,30.655", "distance": "300"},
            {"id": "c2", "name": "咖啡小馆", "type": "餐饮服务;咖啡厅;咖啡厅",
             "typecode": "050500", "location": "104.071,30.655", "distance": "200"},
        ]

    monkeypatch.setattr("app.api.v1.district.place_around", _around)
    async def _detail(poi_id: str):
        return {"typecode": "050117", "rating": 4.5}
    monkeypatch.setattr("app.api.v1.district.place_detail", _detail)

    h = auth_headers(client)
    # 第一次分析：只 c1 是竞品
    snap1 = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=h
    ).json()["snapshot_id"]

    # 把 c2 手动设为竞品
    client.put(
        f"/api/v1/shops/{shop_id}/district/poi-overrides/c2", headers=h,
        json={"is_competitor": True},
    )

    # 第二次分析（新快照）→ c2 仍为竞品且标记 manual
    snap2 = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=h
    ).json()["snapshot_id"]
    comp_ids = {
        c["poi_id"]
        for c in client.get(
            f"/api/v1/shops/{shop_id}/district/snapshots/{snap2}/competitors", headers=h
        ).json()
    }
    assert comp_ids == {"c1", "c2"}

    # 新快照 POI 行带 manual 标记
    detail = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots/{snap2}", headers=h
    ).json()
    c2_row = next(p for p in detail["pois"] if p["poi_id"] == "c2")
    assert c2_row["is_competitor"] is True
    assert c2_row["is_competitor_manual"] is True
    assert snap1 != snap2


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

    async def _detail(poi_id: str):
        return {"rating": 4.8, "cost": 75.0, "business_hours": "17:00-24:00",
                "business_area": "春熙路", "tel": "028-9999", "typecode": "050117", "tag": "火锅"}

    monkeypatch.setattr("app.api.v1.district.place_detail", _detail)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/district/analyze", headers=auth_headers(client)
    )
    snap_id = resp.json()["snapshot_id"]
    comp = client.get(
        f"/api/v1/shops/{shop_id}/district/snapshots/{snap_id}/competitors",
        headers=auth_headers(client),
    )
    assert comp.status_code == 200
    body = comp.json()
    assert len(body) == 1
    assert body[0]["name"] == "隔壁火锅"
    assert body[0]["rating"] == 4.8
    assert body[0]["cost"] == 75.0
    assert body[0]["business_hours"] == "17:00-24:00"
    assert body[0]["business_area"] == "春熙路"
    assert body[0]["tel"] == "028-9999"
    assert body[0]["typecode"] == "050117"


# ============================================================
# map-config
# ============================================================

def test_map_config_503_without_key(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AMAP_JS_KEY", "")
    resp = client.get("/api/v1/district/map-config", headers=auth_headers(client))
    assert resp.status_code == 503


def test_map_config_returns_key(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AMAP_JS_KEY", "js-test-key")
    resp = client.get("/api/v1/district/map-config", headers=auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["amap_js_key"] == "js-test-key"
