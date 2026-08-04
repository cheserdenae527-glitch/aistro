"""商圈分析业务逻辑 — 清洗、竞品映射、统计。

与高德调用（app.services.amap_web）解耦，便于单元测试。
"""
from __future__ import annotations

import difflib
import math
import re
from typing import Any

# 竞品映射表（与 SPEC-DISTRICT v0.5 一致；K1 需按 shops.category 实际枚举核对）
COMPETITOR_TYPES: dict[str, tuple[str, ...]] = {
    "火锅": ("火锅店",),
    "烧烤": ("烧烤",),
    "快餐": ("快餐厅", "小吃快餐店"),
    "咖啡": ("咖啡厅",),
    "甜品/烘焙": ("甜品饮品",),
    "日料": ("日本料理",),
    "西餐": ("西餐厅",),
}

# 自身排除的距离阈值（米）
SELF_DISTANCE_LIMIT_M = 10
# 短名称不参与自身排除
SHORT_NAME_MIN_LEN = 3
# 名称相似度阈值
NAME_SIMILARITY_THRESHOLD = 0.85


def normalize_name(name: str) -> str:
    """归一化名称：去空格/标点，统一小写。"""
    if not name:
        return ""
    cleaned = re.sub(r"[\s，。、！？：；·\-—()（）【】\[\]\x22\x27]", "", name)
    return cleaned.lower()


def is_similar_name(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if len(na) < SHORT_NAME_MIN_LEN or len(nb) < SHORT_NAME_MIN_LEN:
        return False
    if na in nb or nb in na:
        return True
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return ratio >= NAME_SIMILARITY_THRESHOLD


def is_self_poi(poi_name: str, shop_name: str, distance_m: int) -> bool:
    """是否判定为门店自身 POI（名称相似 + 距离 <10m）。"""
    if distance_m >= SELF_DISTANCE_LIMIT_M:
        return False
    return is_similar_name(poi_name, shop_name)


def map_competitor_types(shop_category: str | None) -> tuple[bool, tuple[str, ...]]:
    """竞品映射。返回 (mapping_status is full, competitor_types)。

    - full：category 非空且精确命中映射表
    - none：category 为空或未命中（不做竞品判定）
    """
    if not shop_category:
        return False, ()
    types = COMPETITOR_TYPES.get(shop_category.strip())
    if not types:
        return False, ()
    return True, types


def _poi_type(poi: dict[str, Any]) -> str:
    return str(poi.get("type") or "")


def is_competitor_poi(poi_type: str, competitor_types: tuple[str, ...]) -> bool:
    if not competitor_types:
        return False
    return any(t in poi_type for t in competitor_types)


def parse_poi(
    poi: dict[str, Any],
    shop_name: str,
    competitor_types: tuple[str, ...],
) -> dict[str, Any]:
    """单条高德 POI → 可落库字段。"""
    location = str(poi.get("location") or "")
    lng = lat = None
    try:
        lng_str, lat_str = location.split(",")
        lng, lat = float(lng_str), float(lat_str)
    except (ValueError, TypeError):
        pass

    try:
        distance_m = int(float(poi.get("distance") or 0))
    except (ValueError, TypeError):
        distance_m = 0

    name = str(poi.get("name") or "")
    poi_type = _poi_type(poi)
    excluded = is_self_poi(name, shop_name, distance_m)
    competitor = (not excluded) and is_competitor_poi(poi_type, competitor_types)

    return {
        "poi_id": str(poi.get("id") or ""),
        "name": name,
        "category": poi_type.split(";")[-1] if poi_type else None,
        "address": str(poi.get("address") or "") or None,
        "lng": lng,
        "lat": lat,
        "distance_m": distance_m,
        "is_competitor": competitor,
        "excluded_as_self": excluded,
    }


def compute_stats(pois: list[dict[str, Any]], radius_m: int) -> dict[str, Any]:
    """统计（均基于 excluded_as_self=false 的 POI）。"""
    active = [p for p in pois if not p["excluded_as_self"]]
    poi_total = len(active)
    competitor_count = sum(1 for p in active if p["is_competitor"])

    category_counter: dict[str, int] = {}
    for p in active:
        cat = p["category"] or "未分类"
        category_counter[cat] = category_counter.get(cat, 0) + 1
    category_stats = [
        {"category": k, "count": v}
        for k, v in sorted(category_counter.items(), key=lambda x: -x[1])
    ]

    area_km2 = math.pi * (radius_m / 1000.0) ** 2
    density = round(poi_total / area_km2, 2) if area_km2 > 0 else 0.0

    excluded_self_count = sum(1 for p in pois if p["excluded_as_self"])

    return {
        "poi_total": poi_total,
        "competitor_count": competitor_count,
        "category_stats": category_stats,
        "density_per_km2": density,
        "excluded_self_count": excluded_self_count,
    }
