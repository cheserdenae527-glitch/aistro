"""商圈分析业务逻辑 — 清洗、竞品映射、统计。

与高德调用（app.services.amap_web）解耦，便于单元测试。
"""
from __future__ import annotations

import difflib
import math
import re
from typing import Any

# 竞品映射表（与 SPEC-DISTRICT v0.5 一致；K1 需按 shops.category 实际枚举核对）
# 每类含两路判定信号：
#   type_keywords: type 文本（如「餐饮服务;中餐厅;火锅店」）子串命中
#   typecodes:     高德 POI 分类码（typecode）精确命中（多值以 | 分隔，逐个比对）
# 码值来源：武汉实测高德 Web API / MCP 返回（2026-08）+ 官方分类码表。
#   050117=火锅店 050118=特色/地方风味餐厅(烧烤/私房菜当前均落此码) 050300=快餐厅
#   050301/050302/050303=肯德基/麦当劳/必胜客
#   050500=咖啡厅 050900=甜品店 050800=糕饼店(烘焙) 050202=日本料理 050201=西餐厅(综合风味)
# 注：官方码表 050112=小吃快餐店，但 2026 实测高德对湖北菜馆(鄂菜)也发此码，
#     误纳风险高，故不列入快餐 typecodes（type 关键词「小吃快餐店」仍保留兜底）。
COMPETITOR_TYPES: dict[str, dict[str, tuple[str, ...]]] = {
    "火锅": {"type_keywords": ("火锅店",), "typecodes": ("050117",)},
    "烧烤": {"type_keywords": ("烧烤",), "typecodes": ("050118",)},
    "快餐": {
        "type_keywords": ("快餐厅", "小吃快餐店"),
        "typecodes": ("050300", "050301", "050302", "050303"),
    },
    "咖啡": {"type_keywords": ("咖啡厅",), "typecodes": ("050500",)},
    "甜品/烘焙": {"type_keywords": ("甜品", "糕饼"), "typecodes": ("050900", "050800")},
    "日料": {"type_keywords": ("日本料理",), "typecodes": ("050202",)},
    "西餐": {"type_keywords": ("西餐厅",), "typecodes": ("050201",)},
    "私房菜": {"type_keywords": ("私房菜",), "typecodes": ("050118",)},
}

# 品类别名 → 规范品类（前端已改为下拉，此处兜底 API 创建/历史脏数据的常见写法）
# 仅收录无歧义别名；「私房菜」「饮品/奶茶」等无干净对应类，保持不映射（none）。
_CATEGORY_ALIASES: dict[str, str] = {
    "火锅店": "火锅",
    "重庆火锅": "火锅",
    "四川火锅": "火锅",
    "老火锅": "火锅",
    "烧烤店": "烧烤",
    "烤肉": "烧烤",
    "烤串": "烧烤",
    "快餐店": "快餐",
    "快餐厅": "快餐",
    "小吃快餐": "快餐",
    "小吃": "快餐",
    "简餐": "快餐",
    "咖啡厅": "咖啡",
    "咖啡馆": "咖啡",
    "咖啡店": "咖啡",
    "甜品店": "甜品/烘焙",
    "甜品": "甜品/烘焙",
    "烘焙": "甜品/烘焙",
    "蛋糕": "甜品/烘焙",
    "日本料理": "日料",
    "日式料理": "日料",
    "西餐厅": "西餐",
    "西式": "西餐",
    "私房菜馆": "私房菜",
}


def _canonical_category(shop_category: str) -> str | None:
    """把门店品类归一为映射表 key；无法归一返回 None。"""
    cat = shop_category.strip()
    if cat in COMPETITOR_TYPES:
        return cat
    return _CATEGORY_ALIASES.get(cat)


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


def map_competitor_types(
    shop_category: str | None,
) -> tuple[bool, dict[str, tuple[str, ...]]]:
    """竞品映射。返回 (mapping_status is full, competitor_mapping)。

    - full：category 非空且精确命中映射表
    - none：category 为空或未命中（不做竞品判定）
    - competitor_mapping: {"type_keywords": (...), "typecodes": (...)}
    """
    if not shop_category:
        return False, {}
    canonical = _canonical_category(shop_category)
    mapping = COMPETITOR_TYPES.get(canonical) if canonical else None
    if not mapping:
        return False, {}
    return True, mapping


def _poi_type(poi: dict[str, Any]) -> str:
    return str(poi.get("type") or "")


def _typecode_set(poi_typecode: str) -> set[str]:
    """typecode 可能是多值（| 分隔，如 050302|050900），拆成集合逐个比对。"""
    return {c.strip() for c in poi_typecode.split("|") if c.strip()}


def is_competitor_poi(
    poi_type: str,
    poi_typecode: str,
    competitor_mapping: dict[str, tuple[str, ...]],
) -> bool:
    """竞品判定：type 文本子串命中 **或** typecode 精确命中。"""
    if not competitor_mapping:
        return False
    if any(t in poi_type for t in competitor_mapping.get("type_keywords", ())):
        return True
    wanted = competitor_mapping.get("typecodes", ())
    if wanted and (_typecode_set(poi_typecode) & set(wanted)):
        return True
    return False


def parse_poi(
    poi: dict[str, Any],
    shop_name: str,
    competitor_mapping: dict[str, tuple[str, ...]],
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
    poi_typecode = str(poi.get("typecode") or "")
    excluded = is_self_poi(name, shop_name, distance_m)
    competitor = (not excluded) and is_competitor_poi(
        poi_type, poi_typecode, competitor_mapping
    )

    return {
        "poi_id": str(poi.get("id") or ""),
        "name": name,
        "category": poi_type.split(";")[-1] if poi_type else None,
        "typecode": str(poi.get("typecode") or "") or None,
        "address": str(poi.get("address") or "") or None,
        "tel": str(poi.get("tel") or "") or None,
        "tag": str(poi.get("tag") or "") or None,
        "lng": lng,
        "lat": lat,
        "distance_m": distance_m,
        "is_competitor_auto": competitor,
        "is_competitor": competitor,
        "is_competitor_manual": False,
        "excluded_as_self": excluded,
    }


def merge_competitor_detail(
    item: dict[str, Any],
    detail: dict[str, Any] | None,
) -> dict[str, Any]:
    """把 POI 详情（place/detail）并入竞品条目：评分/人均/营业时间/商圈等。

    detail 缺失或字段为空时保留原值；不覆盖已存在字段（detail 优先）。
    """
    if not detail:
        return item
    for key in ("typecode", "tel", "tag", "business_area", "rating", "cost", "business_hours"):
        value = detail.get(key)
        if value not in (None, ""):
            item[key] = value
    return item


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
