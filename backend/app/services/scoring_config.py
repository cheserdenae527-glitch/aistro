"""博主种草评分配置：默认值 + crawler_config.json 的 blogger_scoring 段覆盖。"""
from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)

DEFAULT_SCORING_CONFIG: dict = {
    "weights": {
        "seeding_depth": 0.25,
        "verticality": 0.20,
        "stable_output": 0.15,
        "sustained_operation": 0.15,
        "growth_trend": 0.15,
        "cost_effectiveness": 0.10,
    },
    "tiers": {
        # min_healthy：加权互动率健康线（百分数口径，闸门3 用）；min_healthy_rate：篇均收藏率健康线（百分数口径，闸门2 辅助信号用）
        # points：加权互动率分档（百分数，interaction_quality 用）；collect/share_rate_points：篇均收藏/分享率分档（百分数）
        "T1": {"min": 1000, "max": 10000, "min_healthy": 6.906, "min_healthy_rate": 1.0, "growth_baseline": 0.06,
               "points": [(6.906, 0), (16.784, 40), (41.851, 70), (74.377, 100)],
               "collect_rate_points": [(0.4, 0), (0.8, 40), (1.5, 70), (3.0, 100)],
               "share_rate_points": [(0.02, 0), (0.05, 40), (0.12, 70), (0.3, 100)]},
        "T2": {"min": 10000, "max": 100000, "min_healthy": 2.946, "min_healthy_rate": 0.6, "growth_baseline": 0.09,
               "points": [(2.946, 0), (7.810, 40), (12.343, 70), (71.005, 100)],
               "collect_rate_points": [(0.2, 0), (0.4, 40), (0.8, 70), (1.5, 100)],
               "share_rate_points": [(0.01, 0), (0.03, 40), (0.08, 70), (0.2, 100)]},
        "T3": {"min": 100000, "max": 1000000, "min_healthy": 1.161, "min_healthy_rate": 0.3, "growth_baseline": 0.08,
               "points": [(1.161, 0), (2.210, 40), (5.202, 70), (13.548, 100)],
               "collect_rate_points": [(0.1, 0), (0.2, 40), (0.4, 70), (0.8, 100)],
               "share_rate_points": [(0.005, 0), (0.015, 40), (0.04, 70), (0.1, 100)]},
        "T4": {"min": 1000000, "max": None, "min_healthy": 0.833, "min_healthy_rate": 0.15, "growth_baseline": 0.07,
               "points": [(0.833, 0), (1.745, 40), (2.367, 70), (2.631, 100)],
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
    "absolute_thresholds": {
        # v1.12：分层绝对值门槛（篇均点赞/篇均赞藏下限，防"互动率虚高但绝对量小"的小号刷量）
        "T1_lt5k": {"likes": 10, "collects": 20},
        "T1_ge5k": {"likes": 20, "collects": 40},
        "T2": {"likes": 50, "collects": 100},
        "T3": {"likes": 500, "collects": 1000},
        "T4": {"likes": 3000, "collects": 6000},
    },
    "authenticity": {
        # v1.12：多维信号打分制真实性闸门
        "threshold": 50,
        "comment_repeat_threshold": 0.3,
        "signals": {
            "fake_ratio":        {"weight": 30, "direct": True},
            "collect_like_band": {"weight": 20, "collect_like_floor": 0.2,
                "bands": {"T1_lt5k": [0.03, 0.15], "T1_ge5k": [0.02, 0.12],
                          "T2": [0.008, 0.06], "T3": [0.004, 0.025], "T4": [0.002, 0.012]}},
            "spam_ratio":        {"weight": 15},
            "abs_likes_floor":   {"weight": 10},
            "same_brand_repeat": {"weight": 10, "max_repeat": 3},
            "commerce_density":  {"weight": 5,
                "max_ratio": {"T1": 0.15, "T2": 0.25, "T3": 0.40, "T4": 0.50}},
            "comment_repeat":    {"weight": 15, "enabled_with_comments": True},
            "like_rate_band":    {"weight": 0, "low": 0.03, "high": 0.08, "commerce_high": 0.10},
            "fans_content_match": {"weight": 0},
            "organic_share":     {"weight": 0, "min_ratio": 0.65},
        },
    },
    "cost": {
        # v1.12：性价比与建议报价（锚点/单价为初值，待真实样本标定）
        "read_rates": {"T1": 0.15, "T2": 0.10, "T3": 0.06, "T4": 0.04},
        "price_anchors": {
            # T2 已按真实样本标定（2026-08-13，蒲公英相似创作者 38 样本 P50）；其余层为初值待标定
            "T1": {"picture": 500, "video": 800},
            "T2": {"picture": 2050, "video": 2800},
            "T3": {"picture": 4000, "video": 6500},
            "T4": {"picture": 12000, "video": 20000},
        },
        "read_unit": {"T1": 30, "T2": 40, "T3": 50, "T4": 60},
        "inter_unit": {"T1": 2.5, "T2": 3.5, "T3": 5, "T4": 8},
        "type_factor": {"picture": 0.8, "video": 1.0},
        "quality_gate": 0.5,
        "quality_hard_gate": 0.3,
        "quality_discount": {"high_band": {"min": 0.5, "slope": 0.5}, "low_band": {"slope": 0.5}},
        "fusion": {"data": 0.7, "anchor": 0.3},
        "bid_weights": {"interaction": 0.6, "read": 0.4},
        "bid_merchant_discount": 0.9,
        "range": [0.85, 1.15],
        "cpm_mismatch": {"yellow": 2.0, "red": 5.0},
        "price_includes_platform_fee": False,
        "points": [(0.6, 100), (1.0, 70), (1.5, 40), (2.0, 10)],
        "industry_benchmarks": {
            "cpe_bands": {"picture": {"excellent": 4, "good": 8, "normal": 15},
                          "video": {"excellent": 6, "good": 12, "normal": 25}},
            "interaction_rate": [0.03, 0.05],
            "viral_ratio": [0.05, 0.08],
            "roi_excellent": 1.5,
            "roi_leading": 2.0,
        },
    },
    "audience": {
        # v1.12：受众画像
        "min_signal_notes": 5,
        "verticality_weight": 0.3,
        "negative_words": ["别", "避雷", "踩雷", "不值", "后悔", "别去", "劝退", "差评", "难吃", "失望"],
        "price_exclude_words": ["卡路里", "热量", "优惠", "满减", "折扣", "限量", "库存", "份", "克", "秒杀", "团购价"],
        "price_patterns": [
            "人均\\s*(\\d+)\\s*元",
            "¥(\\d+)",
            "(\\d+)元/位",
            "(\\d+)[-~至]\\d+元",
            "人均(\\d+)",
        ],
        "level_keywords": {
            "奢华": ["米其林", "黑珍珠", "omakase", "fine dining", "国宴"],
            "高端": ["法餐", "私房菜", "五星", "预约制", "人均500+"],
            "中端": ["商场", "连锁", "网红店", "日料", "西餐", "brunch", "烤肉店"],
            "大众": ["街边", "小吃", "食堂", "夜市", "苍蝇馆子", "大排档", "外卖", "平价"],
        },
        "category_keywords": {
            "火锅": ["火锅", "麻辣烫", "串串"],
            "烧烤": ["烧烤", "烤肉", "烤串"],
            "甜品": ["甜品", "蛋糕", "冰淇淋", "糖水"],
            "咖啡": ["咖啡", "拿铁", "美式", "手冲"],
            "奶茶": ["奶茶", "果茶", "柠檬茶"],
            "川菜": ["川菜", "麻辣"],
            "粤菜": ["粤菜", "茶餐厅", "早茶"],
            "日料": ["日料", "寿司", "居酒屋"],
            "西餐": ["西餐", "牛排", "意面", "brunch"],
            "面馆": ["面馆", "拉面", "小面"],
            "烘焙": ["面包", "烘焙", "可颂"],
        },
        "scene_keywords": {
            "聚餐": ["聚餐", "聚会", "团建"],
            "下午茶": ["下午茶", "下午"],
            "一人食": ["一人食", "一个人"],
            "夜宵": ["夜宵", "深夜"],
            "早餐": ["早餐", "早点"],
            "亲子": ["亲子", "带娃", "孩子"],
            "约会": ["约会", "情侣"],
        },
        "match_threshold": 60,
        "merchant_tier_map": {
            "T1": {"大众": ["街边店", "社区店"], "中端": ["社区品质店", "单店"], "高端": ["精品单店", "预约制"], "奢华": ["小众高端"]},
            "T2": {"大众": ["区域快餐", "平价连锁"], "中端": ["商场店", "区域连锁"], "高端": ["商场中高端", "精品连锁"], "奢华": ["高端餐饮", "奢侈体验"]},
            "T3": {"大众": ["区域连锁快餐", "大众品牌"], "中端": ["连锁品牌", "区域头部"], "高端": ["区域头部", "精品品牌"], "奢华": ["高端品牌", "招商背书"]},
            "T4": {"大众": ["全国大众品牌", "连锁"], "中端": ["全国中端品牌"], "高端": ["全国高端品牌", "平台级"], "奢华": ["头部品牌", "平台级造势"]},
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_config_cache: dict | None = None


def load_scoring_config() -> dict:
    """读取 crawler_config.json 的 blogger_scoring 段并覆盖默认值。

    结果按进程缓存（crawler.config.load_config 每次读文件）；调用方拿到的是
    深拷贝，修改返回值不会污染缓存。需要热更新时调用 clear_scoring_config_cache()。
    """
    global _config_cache
    if _config_cache is None:
        try:
            from crawler.config import load_config

            raw = load_config().get("blogger_scoring") or {}
            _config_cache = _deep_merge(DEFAULT_SCORING_CONFIG, raw)
        except Exception:
            logger.warning("blogger_scoring 配置读取失败，回退默认值", exc_info=True)
            _config_cache = copy.deepcopy(DEFAULT_SCORING_CONFIG)
    return copy.deepcopy(_config_cache)


def clear_scoring_config_cache() -> None:
    """清空配置缓存（配置热更新 / 测试隔离用）。"""
    global _config_cache
    _config_cache = None
