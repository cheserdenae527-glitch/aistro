"""博主种草评分配置：默认值 + crawler_config.json 的 blogger_scoring 段覆盖。"""
from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)

DEFAULT_SCORING_CONFIG: dict = {
    "weights": {
        "seeding_depth": 0.30,
        "verticality": 0.20,
        "stable_output": 0.20,
        "sustained_operation": 0.15,
        "growth_trend": 0.15,
    },
    "tiers": {
        "T1": {"min": 1000, "max": 10000, "min_healthy_rate": 1.0, "growth_baseline": 0.06,
               "collect_rate_points": [(0.4, 0), (0.8, 40), (1.5, 70), (3.0, 100)],
               "share_rate_points": [(0.02, 0), (0.05, 40), (0.12, 70), (0.3, 100)]},
        "T2": {"min": 10000, "max": 100000, "min_healthy_rate": 0.6, "growth_baseline": 0.09,
               "collect_rate_points": [(0.2, 0), (0.4, 40), (0.8, 70), (1.5, 100)],
               "share_rate_points": [(0.01, 0), (0.03, 40), (0.08, 70), (0.2, 100)]},
        "T3": {"min": 100000, "max": 1000000, "min_healthy_rate": 0.3, "growth_baseline": 0.08,
               "collect_rate_points": [(0.1, 0), (0.2, 40), (0.4, 70), (0.8, 100)],
               "share_rate_points": [(0.005, 0), (0.015, 40), (0.04, 70), (0.1, 100)]},
        "T4": {"min": 1000000, "max": None, "min_healthy_rate": 0.15, "growth_baseline": 0.07,
               "collect_rate_points": [(0.05, 0), (0.1, 40), (0.2, 70), (0.4, 100)],
               "share_rate_points": [(0.003, 0), (0.008, 40), (0.02, 70), (0.05, 100)]},
    },
    "verticality": {
        "food_keywords": [
            "探店", "美食", "好吃", "打卡", "菜单", "套餐", "口味", "推荐", "人气",
            "排队", "新店", "必吃", "餐厅", "小吃", "甜品", "咖啡", "奶茶", "火锅", "烧烤",
        ],
        "points": [(0.2, 10), (0.4, 40), (0.6, 70), (0.8, 100)],
    },
    "viral": {"median_multiplier": 3.0, "abs_min": 200, "points": [(0.0, 0), (0.08, 40), (0.1, 70), (0.2, 100)]},
    "stability": {"gap_days": 14, "cliff_drop": 0.5, "cliff_penalty": 25},
    "growth": {"content_weight": 0.3, "points": [(0.0, 15), (0.5, 45), (1.0, 75), (1.2, 100)]},
    "comments": {
        "intent_keywords": ["在哪", "多少钱", "好吃吗", "怎么去", "求地址", "人均", "哪里", "电话", "营业", "菜单"],
        "spam_keywords": ["太棒了", "学习了", "支持", "求链接", "已收藏", "点赞"],
        "negative_keywords": ["广告", "取关", "踩雷", "差评", "失望"],
        "note_limit": 8,
        "per_note": 50,
    },
    "gate": {
        "stale_days": 60,
        "fake_ratio": 0.20,
        "fake_extra_ratio": 0.005,
        "collect_like_ratio_floor": 0.2,
        "spam_ratio_threshold": 0.5,
        "growth_spike": 0.20,
        "growth_interaction_drop": 0.2,
        "t1_growth_spike": 0.35,
    },
    "stage": {"cold_start_fans": 5000, "mature_fans": 10000, "large_fans": 100000},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_scoring_config() -> dict:
    """读取 crawler_config.json 的 blogger_scoring 段并覆盖默认值。"""
    try:
        from crawler.config import load_config

        raw = load_config().get("blogger_scoring") or {}
        return _deep_merge(DEFAULT_SCORING_CONFIG, raw)
    except Exception:
        logger.warning("blogger_scoring 配置读取失败，回退默认值", exc_info=True)
        return copy.deepcopy(DEFAULT_SCORING_CONFIG)
