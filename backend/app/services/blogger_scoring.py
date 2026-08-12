"""博主真实数据评分引擎（C9 设计方案实现）。

原则：只消费真实详情样本；缺失就是缺失，绝不估算、不外推。
结构：四维评分 + 粉丝分层归一化 + 类型内标准化 + 资格闸门（优先于分数）。
阈值：以下均为“结构占位”，需按 DESIGN-BLOGGER-SCORING-REALDATA.md §8 用真实账号标定后替换。
"""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.scoring_config import load_scoring_config
from app.services.blogger_verticality import food_verticality

CN_TZ = timezone(timedelta(hours=8))

# 加权互动：点赞成本最低、最容易刷，权重最低；分享最难伪造，权重最高
LIKES_WEIGHT = 1
COLLECTS_WEIGHT = 4
COMMENTS_WEIGHT = 5
SHARES_WEIGHT = 6

LEVELS = [
    (85, "卓越", "优先入选"),
    (70, "优秀", "推荐入选"),
    (55, "良好", "候选观察"),
    (40, "一般", "暂不推荐"),
    (0, "待观察", "过滤"),
]

ANALYSIS_WINDOW_DAYS = 90
TREND_MIN_SAMPLES = 10
_CONF_RANK = {"high": 0, "medium": 1, "low": 2}
_NONCORE = {"verticality", "stable_output", "sustained_operation", "growth_trend", "cost_effectiveness"}


def _weighted(st: dict) -> int:
    return (
        int(st.get("liked", 0) or 0) * LIKES_WEIGHT
        + int(st.get("collected", 0) or 0) * COLLECTS_WEIGHT
        + int(st.get("comments", 0) or 0) * COMMENTS_WEIGHT
        + int(st.get("shared", 0) or 0) * SHARES_WEIGHT
    )


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CN_TZ)
        return dt.astimezone(CN_TZ)
    except (ValueError, TypeError):
        return None


def _interpolate(points: list[tuple[float, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _tier_for(fans: int) -> dict:
    """粉丝分层：从 scoring_config 读取（唯一事实来源）。

    points/min_healthy 为加权互动率百分数口径，min_healthy_rate 为篇均收藏率
    百分数口径；初版标定 2026-08-08（样本 T1=12 / T2=12 / T3=11 / T4=4），待复核。
    """
    tiers = load_scoring_config()["tiers"]
    for key, t in tiers.items():
        if fans >= int(t["min"]) and (t.get("max") is None or fans < int(t["max"])):
            merged = dict(t)
            merged["tier_name"] = key
            return merged
    merged = dict(tiers["T1"])
    merged["tier_name"] = "T1"
    return merged


def _real_notes(notes: list[dict]) -> list[dict]:
    """准入：详情成功且四项互动字段存在、有发布时间。"""
    real = []
    for n in notes:
        st = n.get("stats") or {}
        if not all(k in st for k in ("liked", "collected", "comments", "shared")):
            continue
        if _parse_dt(n.get("published_at")) is None:
            continue
        real.append(n)
    return real


def _type_standardized(notes: list[dict]) -> list[float]:
    """类型内标准化互动：按类型中位数归一，类型样本<3 时回退账号全类型中位数。"""
    account_median = statistics.median([_weighted(n["stats"]) for n in notes]) if notes else 0.0
    medians: dict[str, float] = {}
    by_type: dict[str, list[int]] = {}
    for n in notes:
        typ = n.get("type") or "normal"
        by_type.setdefault(typ, []).append(_weighted(n["stats"]))
    for typ, vals in by_type.items():
        medians[typ] = statistics.median(vals) if len(vals) >= 3 else account_median
    out = []
    for n in notes:
        typ = n.get("type") or "normal"
        med = medians.get(typ, account_median)
        w = _weighted(n["stats"])
        out.append(w / med * 100.0 if med > 0 else 0.0)
    return out


def _score_interaction_quality(notes: list[dict], fans: int, tier: dict, now: datetime) -> dict:
    cutoff = now - timedelta(days=ANALYSIS_WINDOW_DAYS)
    recent = [n for n in notes if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff]
    if not recent or fans <= 0:
        return {"score": 0.0, "rate": 0.0, "sample": len(recent)}
    total = sum(_weighted(n["stats"]) for n in recent)
    rate = total / fans / len(recent) * 100.0
    score = _interpolate(tier["points"], rate)
    return {"score": round(score, 1), "rate": round(rate, 3), "sample": len(recent)}


def _score_stable_output(notes: list[dict], now: datetime | None = None) -> dict:
    """稳定产出：爆文率（中位数×3，抗刷量拉高均值）×0.7 + 稳健性（连续性/断崖）×0.3。

    弃用 CV：爆款账号方差天然大，CV 会反向惩罚有爆款的账号；改为只罚中断与暴跌。
    gap_days 上报口径：仅当近 30 天存在 ≥gap_days 天的连续无发布空白期时上报实际天数，否则为 0（常规节奏不算空白）。
    """
    cfg = load_scoring_config()
    now = now or datetime.now(CN_TZ)
    if not notes:
        return {"score": 0.0, "confidence": "high", "detail": {"viral_ratio": 0.0, "gap_days": 0, "cliff_detected": False}}

    weighted = [_weighted(n["stats"]) for n in notes]
    median = statistics.median(weighted)
    mean = statistics.fmean(weighted)
    mult = float(cfg["viral"]["median_multiplier"])
    abs_min = int(cfg["viral"]["abs_min"])
    threshold = median * mult if median > 0 else max(mean * mult, abs_min)
    viral_count = sum(1 for w in weighted if w >= threshold)
    viral_ratio = viral_count / len(notes)
    points = cfg["viral"]["points"]  # [(0.0,0),(0.08,40),(0.1,70),(0.2,100)] 升序
    viral_score = _interpolate(points, viral_ratio)

    # 稳健性：近 30 天最长空白期 ≥ gap_days → 扣分；最新30天 vs 前60天 中位数互动跌 >50% → 扣分
    raw_gap = _max_recent_gap_days(notes, now)
    gap_threshold = int(cfg["stability"]["gap_days"])
    # 空白期按设计口径只认 ≥gap_days 的连续无发布期：常规节奏（如隔天一更）不算空白，detail 上报 0
    has_blank_period = raw_gap >= gap_threshold
    gap_days = raw_gap if has_blank_period else 0
    cliff_detected = _interaction_cliff(notes, now, drop=float(cfg["stability"]["cliff_drop"]))
    penalty = float(cfg["stability"]["cliff_penalty"])
    robustness = 100.0 - (penalty if has_blank_period else 0.0) - (penalty if cliff_detected else 0.0)

    score = viral_score * 0.7 + max(0.0, robustness) * 0.3
    return {
        "score": round(score, 1),
        "confidence": "high",
        "detail": {"viral_ratio": round(viral_ratio, 4), "gap_days": gap_days, "cliff_detected": cliff_detected},
    }


def _max_recent_gap_days(notes: list[dict], now: datetime) -> int:
    """近 30 天窗口内连续无发布的最大天数；窗口内无笔记按 30 天计。"""
    cutoff = now - timedelta(days=30)
    in_window = [dt for n in notes if (dt := _parse_dt(n["published_at"])) is not None and dt >= cutoff]
    if not in_window:
        return 30
    in_window.sort()
    max_gap = 0
    prev = cutoff
    for dt in in_window:
        gap = (dt - prev).days
        if gap > max_gap:
            max_gap = gap
        prev = dt
    tail = (now - prev).days
    return max(max_gap, tail)


def _interaction_cliff(notes: list[dict], now: datetime, drop: float = 0.5) -> bool:
    """最新30天 vs 前60天 的标准化互动中位数下降超过 drop 比例则判定断崖。"""
    std = _type_standardized(notes)
    recent, older = [], []
    for n, s in zip(notes, std):
        dt = _parse_dt(n["published_at"])
        if dt is None:
            continue
        if dt >= now - timedelta(days=30):
            recent.append(s)
        elif dt >= now - timedelta(days=90):
            older.append(s)
    if not recent or not older:
        return False
    m_recent = statistics.median(recent)
    m_older = statistics.median(older)
    return m_older > 0 and m_recent < m_older * (1 - drop)


def _score_sustained_operation(notes: list[dict], now: datetime) -> dict:
    cutoff = now - timedelta(days=ANALYSIS_WINDOW_DAYS)
    recent = [n for n in notes if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff]
    weekly = len(recent) / (ANALYSIS_WINDOW_DAYS / 7.0)
    freq = _interpolate([(0.0, 0), (0.5, 30), (1.0, 50), (2.0, 75), (3.0, 100)], weekly)
    latest_dt = max((_parse_dt(n["published_at"]) for n in notes if _parse_dt(n["published_at"]) is not None), default=None)
    if latest_dt is None:
        freshness = 0.0
        stale_days = None
    else:
        stale_days = max(0.0, (now - latest_dt).total_seconds() / 86400.0)
        freshness = _interpolate([(0.0, 100), (7.0, 100), (30.0, 70), (60.0, 40), (float("inf"), 0)], stale_days)
    score = freq * 0.6 + freshness * 0.4
    return {
        "score": round(score, 1),
        "weekly_notes": round(weekly, 2),
        "freshness_days": round(stale_days, 1) if stale_days is not None else None,
    }


def _comment_participation(notes: list[dict]) -> float:
    """评论参与度 = 评论数 / (赞+藏+评+转) 的篇均值；互动全为 0 时取 0。"""
    ratios = []
    for n in notes:
        st = n["stats"]
        total = sum(int(st.get(k, 0) or 0) for k in ("liked", "collected", "comments", "shared"))
        if total > 0:
            ratios.append(int(st.get("comments", 0) or 0) / total)
    return statistics.fmean(ratios) if ratios else 0.0


def _map_comment_participation(ratio: float) -> float:
    """评论参与度映射（结构占位，待标定）：≥0.25→100，0.15→70，0.08→40，0→0。"""
    points = [(0.0, 0), (0.08, 40), (0.15, 70), (0.25, 100)]
    return _interpolate(points, ratio)


def _comment_analysis_detail(comment_analysis: dict | None) -> dict:
    """评论增强信号明细：意向/水评/负面占比 + 样本量；未开启时为空。"""
    if comment_analysis is None:
        return {}
    return {
        "intent_ratio": round(float(comment_analysis.get("intent_ratio", 0.0)), 4),
        "spam_ratio": round(float(comment_analysis.get("spam_ratio", 0.0)), 4),
        "negative_ratio": round(float(comment_analysis.get("negative_ratio", 0.0)), 4),
        "comment_sample": int(comment_analysis.get("sample", 0) or 0),
    }


def _score_seeding_depth(
    notes: list[dict],
    fans: int,
    tier: dict,
    now: datetime,
    comment_analysis: dict | None = None,
) -> dict:
    """种草深度：收藏(想去)45% + 分享(安利)30% + 评论信号25%。

    收藏深度/分享扩散按粉丝分层映射；赞藏比只作展示信号与闸门红旗，不打分。
    评论分析默认关闭：评论子项用参与度近似且 confidence=low、权重 ×0.5 重归一化。
    """
    cutoff = now - timedelta(days=ANALYSIS_WINDOW_DAYS)
    recent = [n for n in notes if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff]
    recent = recent or notes  # 无近90天笔记时回退全量（停更由闸门4兜底）
    if not recent or fans <= 0:
        detail = {
            "collect_rate_percent": 0.0, "collect_like_ratio": 0.0, "share_rate_percent": 0.0,
            "comment_signal": 0.0, "comment_signal_low_conf": True}
        detail.update(_comment_analysis_detail(comment_analysis))
        return {"score": 0.0, "confidence": "high", "detail": detail}

    total_collect = sum(int(n["stats"].get("collected", 0) or 0) for n in recent)
    total_share = sum(int(n["stats"].get("shared", 0) or 0) for n in recent)
    collect_like_ratios = []
    for n in recent:
        liked = int(n["stats"].get("liked", 0) or 0)
        collected = int(n["stats"].get("collected", 0) or 0)
        if liked > 0:
            collect_like_ratios.append(collected / liked)
    collect_like_ratio = statistics.median(collect_like_ratios) if collect_like_ratios else 0.0

    collect_rate_percent = (total_collect / len(recent) / fans) * 100.0
    share_rate_percent = (total_share / len(recent) / fans) * 100.0
    collect_score = _interpolate(tier["collect_rate_points"], collect_rate_percent)
    share_score = _interpolate(tier["share_rate_points"], share_rate_percent)

    comment_low_conf = comment_analysis is None
    if comment_analysis is not None:
        intent = float(comment_analysis.get("intent_ratio", 0.0))
        spam = float(comment_analysis.get("spam_ratio", 0.0))
        comment_score = max(0.0, min(100.0, intent * 100 - spam * 50))
    else:
        comment_score = _map_comment_participation(_comment_participation(recent))

    sub_weights = {"collect": 0.45, "share": 0.30, "comment": 0.25}
    if comment_low_conf:
        sub_weights["comment"] *= 0.5
    total_w = sum(sub_weights.values())
    score = (collect_score * sub_weights["collect"] + share_score * sub_weights["share"]
             + comment_score * sub_weights["comment"]) / total_w
    detail = {
        "collect_rate_percent": round(collect_rate_percent, 3),
        "collect_like_ratio": round(collect_like_ratio, 3),
        "share_rate_percent": round(share_rate_percent, 3),
        "comment_signal": round(comment_score, 1),
        "comment_signal_low_conf": comment_low_conf,
    }
    detail.update(_comment_analysis_detail(comment_analysis))
    return {
        "score": round(score, 1),
        "confidence": "high",
        "detail": detail,
    }


def _score_trend(std_values: list[float], notes: list[dict]) -> dict:
    if len(notes) < TREND_MIN_SAMPLES:
        return {"score": None, "skipped": True, "reason": "样本不足10篇，趋势维度不计分"}
    ordered = sorted(notes, key=lambda n: _parse_dt(n["published_at"]))
    mid = len(ordered) // 2
    earlier = ordered[:mid]
    later = ordered[mid:]
    avg_earlier = statistics.fmean([_weighted(n["stats"]) for n in earlier]) if earlier else 0.0
    avg_later = statistics.fmean([_weighted(n["stats"]) for n in later]) if later else 0.0
    if avg_earlier <= 0:
        ratio = None
        score = 60.0 if avg_later > 0 else 30.0
        note = "前半程互动为0，按中性/从无到有处理" if avg_later > 0 else "后半程无有效互动，趋势偏低"
    elif avg_later <= 0:
        ratio = 0.0
        score = 30.0
        note = "后半程无有效互动，趋势偏低"
    else:
        ratio = avg_later / avg_earlier
        score = _interpolate([(0.5, 15), (0.7, 40), (1.0, 60), (1.5, 85), (2.0, 100)], ratio)
        note = ""
    return {
        "score": round(score, 1),
        "skipped": False,
        "ratio": round(ratio, 3) if ratio is not None else None,
        "note": note,
    }


def _overall_confidence(dimensions: dict, coverage_conf: str) -> str:
    """通用置信度汇总：min(覆盖率可信度, min(已评分维度置信度))。

    v1.12：score=None（未评分/无数据，如无报价的 cost_effectiveness）的维度**不参与**置信度汇总，
    仅"有分数但置信度低"的维度计入 low——避免"无报价 + 无快照"的常见组合被普遍压成 low。
    特例：low 仅来自单个非核心维度，且种草深度非 low 时，整体取 medium。
    覆盖率 low 已在闸门 1 拦截，此处只会是 high/medium。
    """
    if coverage_conf == "low":
        return "low"
    dim_confs = []
    low_dims = []
    for k, d in dimensions.items():
        if d.get("score") is None:
            continue
        conf = d.get("confidence", "low")
        dim_confs.append(conf)
        if conf == "low":
            low_dims.append(k)
    if not dim_confs:
        return "low"
    min_dim = max(dim_confs, key=lambda c: _CONF_RANK[c])  # 最不信任
    if min_dim == "low" and len(low_dims) == 1 and low_dims[0] in _NONCORE \
            and dimensions.get("seeding_depth", {}).get("confidence", "high") != "low":
        return "medium"
    return max([coverage_conf, min_dim], key=lambda c: _CONF_RANK[c])


def _build_timeline(notes: list[dict]) -> dict:
    timed = sorted((_parse_dt(n["published_at"]) for n in notes if _parse_dt(n["published_at"]) is not None))
    if not timed:
        return {"type": "weekly", "items": []}
    buckets: dict[str, dict] = {}
    for n in notes:
        dt = _parse_dt(n["published_at"])
        wk = dt - timedelta(days=dt.weekday())
        key = wk.date().isoformat()
        b = buckets.setdefault(key, {"key": key, "label": f"{wk.month}.{wk.day}", "notes": 0, "likes": 0, "comments": 0, "collects": 0, "shares": 0, "engagement": 0})
        st = n["stats"]
        b["notes"] += 1
        b["likes"] += int(st.get("liked", 0) or 0)
        b["comments"] += int(st.get("comments", 0) or 0)
        b["collects"] += int(st.get("collected", 0) or 0)
        b["shares"] += int(st.get("shared", 0) or 0)
        b["engagement"] += _weighted(st)
    return {"type": "weekly", "items": sorted(buckets.values(), key=lambda b: b["key"])}


def _level_for(score: float) -> tuple[str, str]:
    for threshold, label, desc in LEVELS:
        if score >= threshold:
            return label, desc
    return LEVELS[-1][1], LEVELS[-1][2]


_LEVEL_ORDER = ["待观察", "一般", "良好", "优秀", "卓越"]


def _downgrade_level(level: str) -> str:
    idx = _LEVEL_ORDER.index(level)
    return _LEVEL_ORDER[max(0, idx - 1)]


def _level_desc(level: str) -> str:
    """等级标签对应的描述文案（闸门降级后同步刷新 desc）。"""
    for _, label, d in LEVELS:
        if label == level:
            return d
    return ""


STRONG_SCORE = 70
WEAK_SCORE = 40
STALE_GAP_DAYS = 30
GROWTH_TREND_MIN_SAMPLES = 10

GRASS_WEIGHTS = {"collect_ratio": 0.30, "collect_rate": 0.40, "share_rate": 0.30}
GROWTH_WEIGHTS = {"follower_growth": 0.25, "content_system": 0.20, "update_stability": 0.20, "data_trend": 0.35}

# 种草效率子指标映射（初版占位，待按第七节用真实账号标定）
GRASS_COLLECT_RATE_POINTS = {
    "T1": [(0.0, 0), (1.2, 40), (2.8, 70), (6.0, 100)],
    "T2": [(0.0, 0), (0.8, 40), (1.8, 70), (4.0, 100)],
    "T3": [(0.0, 0), (0.4, 40), (1.0, 70), (2.2, 100)],
    "T4": [(0.0, 0), (0.2, 40), (0.5, 70), (1.2, 100)],
}
GRASS_COLLECT_RATIO_POINTS = [(0.0, 0), (0.15, 40), (0.30, 70), (0.60, 100)]
GRASS_SHARE_RATE_POINTS = {
    "T1": [(0.0, 0), (0.5, 40), (1.2, 70), (3.0, 100)],
    "T2": [(0.0, 0), (0.3, 40), (0.8, 70), (2.0, 100)],
    "T3": [(0.0, 0), (0.2, 40), (0.5, 70), (1.2, 100)],
    "T4": [(0.0, 0), (0.1, 40), (0.3, 70), (0.8, 100)],
}
CONTENT_SYSTEM_POINTS = [(0.0, 0), (0.10, 40), (0.25, 70), (0.50, 100)]


def _tag_counts(notes: list[dict]) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    tagged = 0
    for n in notes:
        tags = n.get("tags") or []
        if not tags:
            continue
        tagged += 1
        for t in tags:
            key = str(t).strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts, tagged


def _content_consistency_multiplier(notes: list[dict]) -> float:
    counts, tagged = _tag_counts(notes)
    if not counts or tagged == 0:
        return 1.0
    total = sum(counts.values())
    concentration = sum((c / total) ** 2 for c in counts.values())
    score = _interpolate(CONTENT_SYSTEM_POINTS, concentration)
    return round(0.7 + 0.3 * (score / 100.0), 3)


def _score_grass_planting(notes: list[dict], fans: int, tier: dict) -> dict:
    """种草效率分 = 赞藏比×0.3 + 收藏率×0.4 + 分享率×0.3，再乘定位一致性系数。"""
    if not notes or fans <= 0:
        return {"score": None, "components": {}, "note": "样本或粉丝数据不足"}
    likes = [int((n.get("stats") or {}).get("liked", 0) or 0) for n in notes]
    collects = [int((n.get("stats") or {}).get("collected", 0) or 0) for n in notes]
    shares = [int((n.get("stats") or {}).get("shared", 0) or 0) for n in notes]
    total_likes = sum(likes)
    total_collects = sum(collects)
    total_shares = sum(shares)
    collect_ratio = total_collects / total_likes if total_likes > 0 else 0.0
    collect_rate = total_collects / fans / len(notes) * 100.0
    share_rate = total_shares / fans / len(notes) * 100.0
    tier_name = str(tier.get("tier_name") or "T1")
    collect_ratio_score = _interpolate(GRASS_COLLECT_RATIO_POINTS, collect_ratio)
    collect_rate_score = _interpolate(GRASS_COLLECT_RATE_POINTS[tier_name], collect_rate)
    share_rate_score = _interpolate(GRASS_SHARE_RATE_POINTS[tier_name], share_rate)
    base_score = (
        collect_ratio_score * GRASS_WEIGHTS["collect_ratio"]
        + collect_rate_score * GRASS_WEIGHTS["collect_rate"]
        + share_rate_score * GRASS_WEIGHTS["share_rate"]
    )
    consistency_mult = _content_consistency_multiplier(notes)
    final_score = min(100.0, base_score * consistency_mult)
    return {
        "score": round(final_score, 1),
        "base_score": round(base_score, 1),
        "consistency_multiplier": consistency_mult,
        "local_match_multiplier": 1.0,
        "components": {
            "collect_ratio": {"score": round(collect_ratio_score, 1), "value": round(collect_ratio, 3), "note": "赞藏比，越接近或超过0.3越偏种草型"},
            "collect_rate": {"score": round(collect_rate_score, 1), "value_percent": round(collect_rate, 3), "note": "篇均收藏率（近似口径）"},
            "share_rate": {"score": round(share_rate_score, 1), "value_percent": round(share_rate, 3), "note": "篇均分享率（近似口径）"},
        },
        "calibrated": False,
        "note": "阈值初版占位，需按设计文档第七节用真实账号标定",
    }


def _score_content_system(notes: list[dict]) -> dict:
    counts, tagged = _tag_counts(notes)
    if not counts or tagged == 0:
        return {"score": 60.0, "detail": {"tag_count": 0, "concentration": 0.0, "note": "无标签数据，按中性处理"}}
    total = sum(counts.values())
    concentration = sum((c / total) ** 2 for c in counts.values())
    score = _interpolate(CONTENT_SYSTEM_POINTS, concentration)
    return {
        "score": round(score, 1),
        "detail": {"tag_count": len(counts), "tagged_notes": tagged, "concentration": round(concentration, 3)},
    }


def _score_update_stability(notes: list[dict], now: datetime) -> dict:
    cutoff = now - timedelta(days=ANALYSIS_WINDOW_DAYS)
    recent = [n for n in notes if _parse_dt(n.get("published_at")) is not None and _parse_dt(n.get("published_at")) >= cutoff]
    weekly = len(recent) / (ANALYSIS_WINDOW_DAYS / 7.0)
    freq_score = _interpolate([(0.0, 0), (0.5, 30), (1.0, 50), (2.0, 75), (3.0, 100)], weekly)
    times = sorted(_parse_dt(n.get("published_at")) for n in notes if _parse_dt(n.get("published_at")) is not None)
    max_gap = 0.0
    for a, b in zip(times, times[1:]):
        max_gap = max(max_gap, (b - a).total_seconds() / 86400.0)
    stale_gap = max_gap > STALE_GAP_DAYS
    score = min(freq_score, 100.0)
    if stale_gap:
        score = min(score, 30.0)
    return {
        "score": round(score, 1),
        "detail": {"weekly_notes": round(weekly, 2), "max_gap_days": round(max_gap, 1), "stale_gap": stale_gap},
    }


def _score_data_trend(notes: list[dict], fans: int) -> dict:
    timed = sorted(
        (n for n in notes if _parse_dt(n.get("published_at")) is not None),
        key=lambda n: _parse_dt(n.get("published_at")),
    )
    if len(timed) < GROWTH_TREND_MIN_SAMPLES:
        return {"score": None, "ratio": None, "note": "样本不足10篇，数据趋势不计分"}
    mid = len(timed) // 2
    earlier = timed[:mid]
    later = timed[mid:]

    def collect_median(items: list[dict]) -> float:
        vals = [int((n.get("stats") or {}).get("collected", 0) or 0) for n in items]
        return statistics.median(vals) if vals else 0.0

    e = collect_median(earlier)
    later_med = collect_median(later)
    if e <= 0:
        ratio = None
        score = 60.0 if later_med > 0 else 30.0
        note = "前半程收藏为0，按中性/从无到有处理" if later_med > 0 else "后半程无有效收藏，趋势偏低"
    elif later_med <= 0:
        ratio = 0.0
        score = 30.0
        note = "后半程无有效收藏，趋势偏低"
    else:
        ratio = later_med / e
        score = _interpolate([(0.5, 15), (0.7, 40), (1.0, 60), (1.5, 85), (2.0, 100)], ratio)
        note = ""
    return {"score": round(score, 1), "ratio": round(ratio, 3) if ratio is not None else None, "note": note}


def _score_follower_growth(history: list[dict]) -> float | None:
    if len(history) < 2:
        return None
    rows = []
    for h in history:
        dt = _parse_dt(h.get("snapshot_at") or h.get("recorded_at") or h.get("created_at"))
        if dt is None:
            continue
        fans = int(h.get("fans", 0) or 0)
        rows.append((dt, fans))
    rows.sort(key=lambda x: x[0])
    if len(rows) < 2:
        return None
    first_fans = rows[0][1]
    last_fans = rows[-1][1]
    if first_fans <= 0:
        return None
    growth_rate = (last_fans - first_fans) / first_fans
    score = _interpolate([(-0.2, 0), (0.0, 40), (0.1, 70), (0.3, 100)], growth_rate)
    return round(score, 1)


def _latest_growth_rate(history: list[dict] | None) -> float | None:
    """取最近两次快照的粉丝增长率并月化；间隔需 ≤60 天，短间隔会被放大（如 1-2 天跨度 ×15-30）。

    不足两次有效快照、间隔 ≤0 或 >60 天返回 None。"""
    if not history or len(history) < 2:
        return None
    items = []
    for h in history:
        dt = _parse_dt(h.get("snapshot_at") or h.get("date") or h.get("created_at"))
        fans = int(h.get("fans", 0) or 0)
        if dt and fans > 0:
            items.append((dt, fans))
    items.sort()
    if len(items) < 2:
        return None
    (dt_prev, fans_prev), (dt_last, fans_last) = items[-2], items[-1]
    days = (dt_last - dt_prev).days
    if days <= 0 or days > 60:
        return None
    if fans_prev <= 0:
        return None
    rate = (fans_last - fans_prev) / fans_prev
    return rate * 30.0 / days  # 月化


def _score_growth_trend(
    notes: list[dict],
    fans: int,
    now: datetime,
    follower_history: list[dict] | None,
    tier: dict,
) -> dict:
    """增长趋势：有快照 → 涨粉分×(1-content_weight) + 内容趋势×content_weight；无快照 → 仅内容趋势，confidence=low。

    无快照时不引入阶段分，避免与阶段判定的同源互动趋势信号重复计算（见设计 §4.5）。
    fans/now 为 Task 9 五维统一调用契约预留，本维度暂未使用。
    """
    # 内容趋势沿用原 `_score_trend` 的加权互动口径（未做类型内标准化）；如需标准化待 Task 9 统一评估
    trend = _score_trend(None, notes)
    content_score = None if trend["skipped"] else trend["score"]
    content_reason = None if not trend["skipped"] else trend["reason"]

    growth_rate = _latest_growth_rate(follower_history)
    if growth_rate is None:
        if content_score is None:
            return {"score": None, "confidence": "low", "detail": {
                "growth_rate": None, "has_snapshot": False, "trend_ratio": None,
                "reason": content_reason or "样本不足以计算内容趋势", "weight_halved": True}}
        return {"score": content_score, "confidence": "low", "detail": {
            "growth_rate": None, "has_snapshot": False, "trend_ratio": trend["ratio"],
            "reason": "无涨粉快照，仅按内容趋势计分", "weight_halved": True}}

    cfg = load_scoring_config()
    baseline = float(tier.get("growth_baseline", 0.08))
    points = cfg["growth"]["points"]  # [(0.0,15),(0.5,45),(1.0,75),(1.2,100)] 升序
    growth_score = _interpolate(points, growth_rate / baseline if baseline else 0.0)
    if content_score is None:
        score = growth_score
        conf = "high"
        detail = {"growth_rate": round(growth_rate, 4), "has_snapshot": True, "trend_ratio": None,
                  "reason": "内容趋势样本不足，仅按涨粉计分"}
    else:
        content_weight = float(cfg["growth"]["content_weight"])
        score = growth_score * (1 - content_weight) + content_score * content_weight
        conf = "high"
        detail = {"growth_rate": round(growth_rate, 4), "has_snapshot": True,
                  "trend_ratio": trend["ratio"], "reason": None}
    return {"score": round(score, 1), "confidence": conf, "detail": detail}


def _weekly_notes(notes: list[dict], now: datetime) -> float:
    cutoff = now - timedelta(days=90)
    recent = 0
    for n in notes:
        dt = _parse_dt(n.get("published_at"))
        if dt is not None and dt >= cutoff:
            recent += 1
    return round(recent / 13.0, 2)  # 90 天 ≈ 13 周


def _classify_stage(fans: int, notes: list[dict], now: datetime, follower_history: list[dict] | None) -> dict:
    """账号阶段：冷启动 / 成长 / 成熟 / 衰退。独立输出标签，不参与加权。

    有 ≥2 次快照 → 涨粉率 vs 分层基准 + 更新频率，置信 high/medium；
    无快照 → 粉丝量级 + 更新频率 + 互动趋势推断，置信度恒为 low。
    """
    cfg = load_scoring_config()
    tier = _tier_for(fans)
    baseline = float(tier.get("growth_baseline", 0.08))
    weekly = _weekly_notes(notes, now)
    growth_rate = _latest_growth_rate(follower_history)
    latest_dt = None
    for n in notes:
        dt = _parse_dt(n.get("published_at"))
        if dt and (latest_dt is None or dt > latest_dt):
            latest_dt = dt
    days = (now - latest_dt).days if latest_dt is not None else None
    stale = days is not None and days > int(cfg["gate"]["stale_days"])

    if growth_rate is not None:
        # 0.3×baseline 处刻意取严格 <：恰好达标视为「维持存量」而非衰退，避免临界样本误判
        if growth_rate <= 0 or (growth_rate < baseline * 0.3 and weekly < 1.0):
            label, conf = "衰退", "medium"
        elif growth_rate >= baseline:
            label, conf = "成长", "high"
        elif fans >= int(cfg["stage"]["mature_fans"]) and weekly >= 1.0:
            label, conf = "成熟", "medium"
        else:
            label, conf = "冷启动", "medium"
        if stale and label in ("成长", "成熟"):
            label, conf = "衰退", "medium"
        evidence = [f"月化涨粉 {growth_rate * 100:.1f}%", f"周均发布 {weekly}"]
        if stale:
            evidence.append(f"最新笔记发布距今 {days} 天（停更）")
    else:
        # 无快照：仅推断，恒 low；冷启动仅限粉丝 < cold_start_fans
        if stale:
            label = "衰退"
        elif fans < int(cfg["stage"]["cold_start_fans"]):
            label = "冷启动"
        elif weekly >= 1.0 and fans >= int(cfg["stage"]["large_fans"]):
            label = "成熟"
        elif weekly >= 1.0:
            label = "成长"
        else:
            label = "成熟"  # 粉丝达标但低频、未停更：存量成熟账号
        conf = "low"
        evidence = [f"粉丝 {fans}", f"周均发布 {weekly}", "近 60 天无有效涨粉快照，阶段为推断"]
        if stale:
            evidence.append(f"最新笔记发布距今 {days} 天（停更）")
    return {"label": label, "confidence": conf, "evidence": evidence}


def _growth_anomaly(growth_rate: float, interaction_drop: float, fans: int) -> dict | None:
    """闸门 5：涨粉异常 = 增幅超阈值 且 同期互动率下降（「且」关系）。

    T1（<1w 粉）阈值放宽到 t1_growth_spike，避免小爆款有机增长误报。
    """
    cfg = load_scoring_config()["gate"]
    spike = float(cfg["t1_growth_spike"]) if fans < 10000 else float(cfg["growth_spike"])
    if growth_rate > spike and interaction_drop >= float(cfg["growth_interaction_drop"]):
        return {"type": "growth_anomaly", "level": "warn",
                "detail": f"粉丝增幅 {growth_rate * 100:.0f}% 且互动率下降，疑似注水"}
    return None


def _collect_like_inversion_hit(notes: list[dict], fans: int, tier: dict) -> bool:
    """刷量辅助信号：赞藏比中位数 <0.2 且 篇均收藏/粉丝 低于该层最低健康线。"""
    cfg = load_scoring_config()["gate"]
    ratios = []
    for n in notes:
        liked = int(n["stats"].get("liked", 0) or 0)
        collected = int(n["stats"].get("collected", 0) or 0)
        if liked > 0:
            ratios.append(collected / liked)
    if not ratios:
        return False
    median_ratio = statistics.median(ratios)
    if median_ratio >= float(cfg["collect_like_ratio_floor"]):
        return False
    collect_rate_percent = sum(int(n["stats"].get("collected", 0) or 0) for n in notes) / len(notes) / fans * 100.0
    # 篇均收藏率（百分数）低于该层收藏健康线（min_healthy_rate，百分数口径）
    return collect_rate_percent < float(tier["min_healthy_rate"])


def _summarize_follower_history(history: list[dict] | None) -> dict | None:
    """汇总粉丝历史来源与增长信息，供前端展示和成长潜力子项明细使用。"""
    if not history:
        return None
    rows = []
    for h in history:
        dt = _parse_dt(h.get("snapshot_at") or h.get("recorded_at") or h.get("created_at"))
        if dt is None:
            continue
        fans = int(h.get("fans", 0) or 0)
        if fans <= 0:
            continue
        rows.append({"dt": dt, "fans": fans, "source": h.get("source") or "local"})
    rows.sort(key=lambda r: r["dt"])
    if len(rows) < 2:
        return None
    first = rows[0]
    last = rows[-1]
    growth_rate = (last["fans"] - first["fans"]) / first["fans"] if first["fans"] else 0.0
    days = max((last["dt"] - first["dt"]).days, 1)
    platform_points = sum(1 for r in rows if r["source"] == "justoneapi")
    local_points = len(rows) - platform_points
    return {
        "source": "justoneapi" if platform_points >= 2 else ("local" if local_points >= 2 else "mixed"),
        "points": len(rows),
        "platform_points": platform_points,
        "local_points": local_points,
        "start_fans": first["fans"],
        "end_fans": last["fans"],
        "fans_increase": last["fans"] - first["fans"],
        "growth_rate": round(growth_rate, 4),
        "days": days,
        "start_date": first["dt"].date().isoformat(),
        "end_date": last["dt"].date().isoformat(),
        "series": [{"fans": r["fans"], "snapshot_at": r["dt"].isoformat(), "source": r["source"]} for r in rows],
    }


def _score_growth_potential(notes: list[dict], fans: int, now: datetime, follower_history: list[dict] | None = None) -> dict:
    """成长潜力分 = 粉丝增长×0.25 + 内容系统化×0.20 + 更新稳定性×0.20 + 数据趋势×0.35。"""
    weights = dict(GROWTH_WEIGHTS)
    components: dict[str, dict] = {}
    if follower_history:
        follower_score = _score_follower_growth(follower_history)
        if follower_score is not None:
            summary = _summarize_follower_history(follower_history) or {}
            components["follower_growth"] = {
                "score": follower_score,
                "detail": {
                    "snapshots": len(follower_history),
                    **{k: v for k, v in summary.items() if k != "series"},
                },
            }
        else:
            del weights["follower_growth"]
            components["follower_growth"] = {"score": None, "detail": {"note": "粉丝历史快照不足2次"}}
    else:
        del weights["follower_growth"]
        components["follower_growth"] = {"score": None, "detail": {"note": "暂无粉丝历史快照，该子项不计分"}}
    components["content_system"] = _score_content_system(notes)
    components["update_stability"] = _score_update_stability(notes, now)
    trend = _score_data_trend(notes, fans)
    if trend["score"] is None:
        del weights["data_trend"]
        components["data_trend"] = {"score": None, "detail": {"note": trend["note"]}}
    else:
        components["data_trend"] = {"score": trend["score"], "detail": {"ratio": trend["ratio"], "note": trend["note"]}}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return {"score": None, "components": components, "note": "无可用成长指标"}
    score = sum(components[k]["score"] * weights[k] for k in weights if components[k].get("score") is not None) / total_weight
    return {"score": round(score, 1), "components": components, "note": "成长潜力分按可用子项归一化计算"}


def _build_decision(grass: dict, growth: dict) -> dict:
    if grass is None or growth is None:
        return {"status": "no_data", "quadrant": "数据不足", "recommendation": "数据不足，暂不评分"}
    g = grass.get("score")
    p = growth.get("score")
    if g is None or p is None:
        return {"status": "no_data", "quadrant": "数据不足", "recommendation": "数据不足，暂不评分"}

    def level_label(v: float) -> str:
        return "强" if v >= STRONG_SCORE else ("中" if v >= WEAK_SCORE else "弱")

    gl = level_label(g)
    pl = level_label(p)
    if gl == "强" and pl == "强":
        quadrant = "首选合作"
        rec = "优先投放，可谈长期框架合作"
    elif gl == "强":
        quadrant = "短期投放"
        rec = "适合短期投放、单篇合作，不做长期绑定"
    elif pl == "强":
        quadrant = "潜力股"
        rec = "低价提前绑定，长期观察，定期复核"
    else:
        quadrant = "过滤"
        rec = "暂不合作"
    return {"status": "ok", "quadrant": quadrant, "recommendation": rec, "grass_level": gl, "growth_level": pl}


def _recommendation(
    overall: float, stage: dict, anomalies: list[dict],
    cost_score: float | None = None, match_score: float | None = None,
) -> tuple[str, str]:
    """合作建议：priority / ok / caution 三档（insufficient/not_recommended 已提前返回）。

    v1.12：info 级红旗（audience_mismatch）不降档；优先合作要求 性价比≥60（有报价时）且 匹配≥60（有 profile 时）。
    """
    red_flag_types = {a["type"] for a in anomalies if a.get("level") != "info"}
    has_any_flag = bool(red_flag_types)
    stage_ok = stage["label"] in ("成长", "成熟") and stage["confidence"] != "low"
    cost_ok = cost_score is None or cost_score >= 60
    match_ok = match_score is None or match_score >= 60
    if overall >= 70 and not has_any_flag and stage_ok and cost_ok and match_ok:
        return "priority", "美食垂直度高、种草能力强，处于成长/成熟期，性价比与目标匹配达标，适合优先建联"
    if overall >= 55 and not has_any_flag:
        return "ok", "种草能力在线且无红旗，可以合作"
    return "caution", "存在非致命红旗或分数偏低，建议谨慎评估"


def _build_reasons(dimensions: dict, stage: dict) -> list[str]:
    reasons = []
    v = dimensions["verticality"]["detail"]
    if v.get("food_ratio", 0) >= 0.6:
        reasons.append(f"美食内容占比 {v['food_ratio'] * 100:.0f}%")
    sd = dimensions["seeding_depth"]["detail"]
    if sd.get("collect_rate_percent", 0) > 0:
        reasons.append(f"篇均收藏率 {sd['collect_rate_percent']:.2f}%")
    gt = dimensions["growth_trend"]["detail"]
    if gt.get("has_snapshot") and gt.get("growth_rate") is not None:
        reasons.append(f"月化涨粉 {gt['growth_rate'] * 100:.1f}%")
    reasons.append(f"账号阶段：{stage['label']}")
    return reasons


def score_blogger(
    notes: list[dict],
    follower_count: int = 0,
    total_notes: int = 0,
    now: datetime | None = None,
    sampled: bool = False,
    coverage_denominator: int | None = None,
    follower_history: list[dict] | None = None,
    comment_analysis: dict | None = None,
    pgy_meta: dict | None = None,
    merchant_profile: dict | None = None,
) -> dict:
    """运行种草能力五维评分，返回可直接落库/展示的结果结构。"""
    now = now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)

    real = _real_notes(notes)
    fetched = len(real)
    sample_size = coverage_denominator if coverage_denominator is not None else total_notes
    coverage_rate = fetched / sample_size if sample_size else 0.0
    if coverage_rate >= 0.8 and fetched >= 30:
        coverage_conf = "high"
    elif coverage_rate >= 0.5 and fetched >= 15:
        coverage_conf = "medium"
    else:
        coverage_conf = "low"

    base = {
        "note_count": len(notes),
        "real_note_count": fetched,
        "sampled": bool(sampled),
        "coverage": {
            "total_notes": total_notes,
            "sample_size": sample_size,
            "fetched_notes": fetched,
            "coverage_rate": round(coverage_rate, 4),
        },
        "confidence": coverage_conf,
        "dimensions": {},
        "overall": None,
        "overall_score_suppressed": False,
        "grass_planting": None,
        "growth_potential": None,
        "decision": None,
        "stage": None,
        "follower_history": _summarize_follower_history(follower_history),
        "anomalies": [],
        "insights": [],
        "timeline": _build_timeline(real),
        "notes": sorted(real, key=lambda n: n.get("published_at") or "", reverse=True),
    }

    if sampled and sample_size:
        base["insights"].append(f"抽样分析：共 {total_notes} 篇，均匀抽取 {sample_size} 篇真实详情")

    # 闸门 1：覆盖率不达标 → insufficient_data（不评分、不判定低质）
    if coverage_conf == "low":
        base["insights"].append("数据不足，暂不评分")
        base["overall_score_suppressed"] = True
        base["decision"] = {
            "recommendation": "insufficient_data", "summary": "真实样本覆盖率不足，暂不评分",
            "reasons": [f"已验证样本 {fetched}/{sample_size or 0}，覆盖率 {coverage_rate:.0%}"],
            "red_flags": [], "low_quality": False,
            "status": "no_data", "quadrant": "数据不足", "grass_level": None, "growth_level": None,
        }
        return base

    tier = _tier_for(follower_count)
    cfg = load_scoring_config()
    gate_cfg = cfg["gate"]
    # v1.12：真实性闸门 / 受众画像 / 性价比（先于五维，供后续降级/集成）
    authenticity = _authenticity_gate(real, follower_count, comment_analysis, pgy_meta, cfg)
    audience = _score_audience_profile(real, tier, cfg)
    pgy_price = (pgy_meta or {}).get("price") if pgy_meta else None
    cost = _score_cost_effectiveness(real, follower_count, tier, pgy_price, pgy_meta, authenticity, cfg)
    # 兼容字段（前端过渡期保留；新前端切走后移除）
    grass = _score_grass_planting(real, follower_count, tier)
    growth = _score_growth_potential(real, follower_count, now, follower_history)
    base["grass_planting"] = grass
    base["growth_potential"] = growth
    old_decision = _build_decision(grass, growth)  # 旧前端兼容（Task 13 切走后移除）

    # 五维评分
    seeding = _score_seeding_depth(real, follower_count, tier, now, comment_analysis=comment_analysis)
    vert = food_verticality(real)
    stable = _score_stable_output(real, now)
    sustained = _score_sustained_operation(real, now)
    growth_trend = _score_growth_trend(real, follower_count, now, follower_history, tier)

    dimensions = {
        "seeding_depth": {"score": seeding["score"], "confidence": seeding["confidence"], "detail": seeding["detail"]},
        "verticality": {"score": vert["score"], "confidence": vert["confidence"], "detail": vert["detail"]},
        "stable_output": {"score": stable["score"], "confidence": stable["confidence"], "detail": stable["detail"]},
        "sustained_operation": {"score": sustained["score"], "confidence": "high", "detail": {"weekly_notes": sustained["weekly_notes"], "freshness_days": sustained["freshness_days"]}},
        "growth_trend": {"score": growth_trend["score"], "confidence": growth_trend["confidence"], "detail": growth_trend["detail"]},
        "cost_effectiveness": {"score": cost["score"], "confidence": cost["confidence"], "detail": cost["detail"]},
    }
    base["dimensions"] = dimensions

    # v1.12：受众画像（顶层 + 垂直度深化）
    base["audience"] = audience
    dimensions["verticality"]["detail"]["audience"] = audience
    if audience["confidence"] == "high" and dimensions["verticality"]["score"] is not None:
        dimensions["verticality"]["score"] = round(
            0.7 * dimensions["verticality"]["score"] + 0.3 * audience["verticality_audience_score"], 1
        )
    else:
        base["insights"].append("受众画像样本不足，垂直度仅按品类评估")

    base["confidence"] = _overall_confidence(dimensions, coverage_conf)

    # 权重归一化（v1.12 §6.2 通用公式：score=None 剔除；low/medium ×0.5；high 原值）
    weights = dict(cfg["weights"])
    w_eff: dict[str, float] = {}
    for k, w in weights.items():
        dim = dimensions[k]
        if dim.get("score") is None:
            continue
        w_eff[k] = w * (0.5 if dim.get("confidence") != "high" else 1.0)
    if growth_trend["score"] is None:
        base["insights"].append(growth_trend["detail"].get("reason") or "增长趋势样本不足，跳过")
    if cost["score"] is None:
        base["insights"].append("暂无蒲公英报价，性价比未评分")
    if not authenticity["passed"] and not authenticity["direct_fail"]:
        base["insights"].append("数据真实性存疑，不提供报价参考")
    total_weight = sum(w_eff.values())
    if total_weight <= 0:
        base["overall"] = None
        base["overall_score_suppressed"] = True
        base["decision"] = {"recommendation": "insufficient_data", "summary": "无可用评分维度", "reasons": [], "red_flags": [], "low_quality": False}
        return base
    overall = sum(dimensions[k]["score"] * w_eff[k] for k in w_eff) / total_weight
    overall = round(overall, 1)
    level, desc = _level_for(overall)

    # 闸门 2：刷量嫌疑（含赞藏比倒挂辅助）
    likes = [int(n["stats"].get("liked", 0) or 0) for n in real]
    median_likes = statistics.median(likes) if likes else 0.0
    fake_hits = 0
    if median_likes > 0:
        for n in real:
            st = n["stats"]
            liked = int(st.get("liked", 0) or 0)
            extra = int(st.get("collected", 0) or 0) + int(st.get("comments", 0) or 0) + int(st.get("shared", 0) or 0)
            if liked >= median_likes * 3 and (extra / liked if liked else 0) < float(gate_cfg["fake_extra_ratio"]):
                fake_hits += 1
    fake_ratio = fake_hits / len(real) if real else 0.0
    collect_inversion = follower_count > 0 and _collect_like_inversion_hit(real, follower_count, tier)
    spam_flag = bool(
        comment_analysis
        and float(comment_analysis.get("spam_ratio", 0.0)) >= float(gate_cfg["spam_ratio_threshold"])
    )
    if fake_ratio > float(gate_cfg["fake_ratio"]) or collect_inversion or spam_flag:
        spam_only = spam_flag and not (
            fake_ratio > float(gate_cfg["fake_ratio"]) or collect_inversion
        )
        base["anomalies"].append({
            "type": "fake_engagement", "level": "block",
            "detail": "疑似刷量（水评占比过高）" if spam_only else "疑似刷量（赞藏倒挂或互动结构异常）",
        })
        base["overall"] = None
        base["overall_score_suppressed"] = True
        base["grass_planting"] = None
        base["growth_potential"] = None
        base["decision"] = {
            "recommendation": "not_recommended", "summary": "疑似刷量，不建议合作",
            "reasons": ["评论区水评占比过高"] if spam_only else ["互动结构异常（高赞低藏或赞藏比倒挂）"],
            "red_flags": [
                {"type": "fake_engagement", "level": "block", "detail": "疑似刷量"}],
            "low_quality": True,
            "status": "blocked", "quadrant": "一票否决", "grass_level": None, "growth_level": None,
        }
        base["insights"].append("疑似刷量，不建议合作")
        return base

    # 阶段判定（独立标签）
    stage = _classify_stage(follower_count, real, now, follower_history)
    base["stage"] = stage

    # 闸门 3：粉丝互动倒挂（粉丝数未知时不判定）
    if follower_count > 0:
        iq_rate = _score_interaction_quality(real, follower_count, tier, now)["rate"]
        if iq_rate < float(tier["min_healthy"]):
            base["anomalies"].append({"type": "interaction_inversion", "level": "cap", "detail": "粉丝互动倒挂"})
            level = "待观察"
            desc = "粉丝互动倒挂，等级封顶待观察"

    # 闸门 4：发布停滞（有意叠加：维度已在新鲜度吃亏，等级再降一档）
    if sustained["freshness_days"] is not None and sustained["freshness_days"] > int(gate_cfg["stale_days"]):
        base["anomalies"].append({"type": "stale", "level": "downgrade", "detail": "最新笔记发布时间超过60天"})
        level = _downgrade_level(level)
        desc = _level_desc(level)
        base["insights"].append("账号可能已停更")

    # 闸门 5：涨粉异常（且关系，T1 放宽）
    if growth_rate := _latest_growth_rate(follower_history):
        std_now = _type_standardized(real)
        recent_std = [s for n, s in zip(real, std_now) if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= now - timedelta(days=30)]
        older_std = [s for n, s in zip(real, std_now) if _parse_dt(n["published_at"]) is not None and now - timedelta(days=90) <= _parse_dt(n["published_at"]) < now - timedelta(days=30)]
        m_recent = statistics.median(recent_std) if recent_std else 0.0
        m_older = statistics.median(older_std) if older_std else 0.0
        interaction_drop = max(0.0, 1.0 - (m_recent / m_older if m_older > 0 else 0.0))
        flag = _growth_anomaly(growth_rate, interaction_drop, follower_count)
        if flag:
            base["anomalies"].append(flag)
            base["insights"].append(flag["detail"])

    # v1.12：商家匹配 + 非致命/信息型红旗 + reasons 扩展
    match = _audience_match(audience, merchant_profile, tier, cfg)
    base["audience"]["match"] = match
    if not authenticity["passed"] and not authenticity["direct_fail"]:
        base["anomalies"].append({"type": "authenticity_failed", "level": "flag", "detail": "数据真实性存疑（多维信号命中）"})
    if cost["score"] is not None and cost["score"] < 40 \
            and float(cost["detail"].get("quality_q") or 1.0) < float(cfg["cost"]["quality_gate"]):
        base["anomalies"].append({"type": "overpriced_low_quality", "level": "flag", "detail": "报价虚高且互动质量不足"})
    if match["score"] is not None and match["score"] < float(cfg["audience"]["match_threshold"]):
        base["anomalies"].append({
            "type": "audience_mismatch", "level": "info",
            "detail": f"商家目标匹配度低（{match['score']}分）：" + ("；".join(match["mismatches"]) if match["mismatches"] else "目标客群不匹配"),
        })
    reasons = _build_reasons(dimensions, stage)
    if cost["score"] is not None:
        d = cost["detail"]
        reasons.append(
            f"性价比 {cost['score']:.0f} 分（图文建议 {d.get('suggested_bid_picture')} 元，"
            f"视频建议 {d.get('suggested_bid_video')} 元）"
        )
    if audience["dominant_level"]:
        mtext = "、".join(audience["merchant_tiers"]) if audience["merchant_tiers"] else ""
        reasons.append(f"受众以{audience['dominant_level']}消费为主" + (f"，适配{mtext}" if mtext else ""))
    if match["score"] is not None:
        reasons.append(f"商家目标匹配度 {match['score']} 分")

    # 合作建议（严格互斥顺序判定）
    recommendation, rec_summary = _recommendation(overall, stage, base["anomalies"], cost["score"], match["score"])
    base["overall"] = {"score": overall, "level": level, "description": desc, "score_suppressed": False}
    base["decision"] = {
        "recommendation": recommendation,
        "summary": rec_summary,
        "reasons": reasons,
        "red_flags": [{"type": a["type"], "level": a["level"], "detail": a["detail"]} for a in base["anomalies"]],
        "low_quality": False,
        # 旧前端兼容字段（Task 13 切走后移除）
        "status": old_decision.get("status"),
        "quadrant": old_decision.get("quadrant"),
        "grass_level": old_decision.get("grass_level"),
        "growth_level": old_decision.get("growth_level"),
    }
    base["insights"].append(f"综合评分 {overall}，等级：{level}；阶段：{stage['label']}")
    return base


# ---------------------------------------------------------------------------
# v1.12：真实性闸门 / 受众画像 / 性价比 / 商家匹配
# ---------------------------------------------------------------------------

def _tier_key(fans: int) -> str:
    """绝对门槛/分层区间用的细粒度 key（T1 按 <5k/≥5k 拆）。"""
    if fans < 5000:
        return "T1_lt5k"
    if fans < 10000:
        return "T1_ge5k"
    if fans < 100000:
        return "T2"
    if fans < 1000000:
        return "T3"
    return "T4"


def _percentile(sorted_values: list[float], pct: int) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct / 100.0
    lo = int(k)
    hi = min(int(k) + 1, len(sorted_values) - 1)
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo))


def _compute_fake_ratio(notes: list[dict], gate_cfg: dict) -> float:
    likes = [int(n["stats"].get("liked", 0) or 0) for n in notes]
    median_likes = statistics.median(likes) if likes else 0.0
    if median_likes <= 0:
        return 0.0
    fake = 0
    for n in notes:
        st = n["stats"]
        liked = int(st.get("liked", 0) or 0)
        extra = int(st.get("collected", 0) or 0) + int(st.get("comments", 0) or 0) + int(st.get("shared", 0) or 0)
        if liked >= median_likes * 3 and (extra / liked if liked else 0) < float(gate_cfg["fake_extra_ratio"]):
            fake += 1
    return fake / len(notes) if notes else 0.0


def _authenticity_gate(
    notes: list[dict],
    follower_count: int,
    comment_analysis: dict | None,
    pgy_meta: dict | None,
    cfg: dict,
) -> dict:
    """多维信号打分制真实性闸门（v1.12）。返回 {passed, score, direct_fail, hits}。"""
    a_cfg = cfg["authenticity"]
    threshold = int(a_cfg["threshold"])
    signals = a_cfg["signals"]
    gate_cfg = cfg["gate"]
    score, hits, direct_fail = 0, [], False

    # 信号1：刷量结构异常（强信号，直接判）
    fake_ratio = _compute_fake_ratio(notes, gate_cfg)
    collect_inversion = follower_count > 0 and _collect_like_inversion_hit(notes, follower_count, _tier_for(follower_count))
    if fake_ratio > float(gate_cfg["fake_ratio"]) or collect_inversion:
        hits.append({"id": "fake_ratio", "weight": 30, "detail": f"fake_ratio={fake_ratio:.2f} 或赞藏倒挂"})
        score += 30
        direct_fail = True

    # 信号2：赞藏量级双向异常（按层区间，任一命中记满 20，不叠加）
    key = _tier_key(follower_count)
    band = signals["collect_like_band"]["bands"][key]
    _fans = max(1, follower_count)
    _cnt = max(1, len(notes))
    avg_cl = (
        sum(int(n["stats"].get("collected", 0) or 0) + int(n["stats"].get("liked", 0) or 0) for n in notes)
        / _cnt / _fans
    )
    ratio_list = [
        n["stats"]["collected"] / max(1, n["stats"]["liked"])
        for n in notes
        if int(n["stats"].get("liked", 0) or 0) > 0
    ]
    median_cl_ratio = statistics.median(ratio_list) if ratio_list else 0.0
    cl_floor = float(signals["collect_like_band"]["collect_like_floor"])
    hit2 = ""
    if avg_cl < band[0]:
        hit2 = f"篇均(赞+藏)/粉丝={avg_cl:.4f} < 下界{band[0]}"
    elif avg_cl > band[1]:
        hit2 = f"篇均(赞+藏)/粉丝={avg_cl:.4f} > 上界{band[1]}"
    if median_cl_ratio < cl_floor:
        hit2 = (hit2 + "；" if hit2 else "") + f"藏/赞中位={median_cl_ratio:.3f} < {cl_floor}"
    if hit2:
        hits.append({"id": "collect_like_band", "weight": 20, "detail": hit2})
        score += 20

    # 信号3：水评占比
    if comment_analysis and float(comment_analysis.get("spam_ratio", 0.0)) >= float(gate_cfg["spam_ratio_threshold"]):
        hits.append({"id": "spam_ratio", "weight": 15, "detail": f"水评占比={comment_analysis['spam_ratio']:.2f}"})
        score += 15

    # 信号4：篇均点赞绝对值下限（按层）
    abs_likes = sum(int(n["stats"].get("liked", 0) or 0) for n in notes) / _cnt
    min_likes = float(cfg["absolute_thresholds"][key]["likes"])
    if abs_likes < min_likes:
        hits.append({"id": "abs_likes_floor", "weight": 10, "detail": f"篇均赞={abs_likes:.1f} < 层下限{min_likes}"})
        score += 10

    # 信号5：商单密度（低权重，按层放宽）
    if pgy_meta and pgy_meta.get("business_note_count") and pgy_meta.get("total_notes"):
        density = int(pgy_meta["business_note_count"]) / max(1, int(pgy_meta["total_notes"]))
        max_ratio = float(signals["commerce_density"]["max_ratio"].get(_tier_for(follower_count)["tier_name"], 0.5))
        if density > max_ratio:
            hits.append({"id": "commerce_density", "weight": 5, "detail": f"商单占比={density:.0%} > 层阈值{max_ratio:.0%}"})
            score += 5

    # 信号6：评论模板重复度（无语义模板；问询意图内容已排除，仅统计 spam 类）
    if comment_analysis:
        repeat = float(comment_analysis.get("template_repeat_ratio", 0.0))
        if repeat >= float(a_cfg.get("comment_repeat_threshold", 0.3)):
            hits.append({"id": "comment_repeat", "weight": 15, "detail": f"无语义模板重复占比={repeat:.2f}"})
            score += 15

    # 信号7-10（C档占位）：same_brand_repeat / like_rate_band / fans_content_match / organic_share
    # 配置 weight>0 且数据接入后启用；当前均未接入，跳过

    passed = (not direct_fail) and (score < threshold)
    return {"passed": passed, "score": score, "direct_fail": direct_fail, "hits": hits}


def _score_audience_profile(notes: list[dict], tier: dict, cfg: dict) -> dict:
    """受众画像（v1.12）：层级分布 / 人均区间 / 品类场景 / 商家适配 / 垂直度深化。"""
    a_cfg = cfg["audience"]
    min_signal = int(a_cfg["min_signal_notes"])
    neg_words = a_cfg["negative_words"]
    exclude_words = a_cfg["price_exclude_words"]
    level_kw = a_cfg["level_keywords"]
    cat_kw = a_cfg["category_keywords"]
    scene_kw = a_cfg["scene_keywords"]
    # v1.12：逐个 pattern 单独编译（备选拼接会把各备选的捕获组按位置重编号，
    # 导致非首个备选命中时 group(1) 为 None；单独编译各自用自己的 group(1)）
    price_patterns = [re.compile(p) for p in a_cfg["price_patterns"]]
    tier_name = tier["tier_name"]

    price_hits: list[float] = []
    level_counts = {k: 0 for k in level_kw}
    cat_counts: dict[str, int] = {}
    scene_counts: dict[str, int] = {}
    signal_notes = 0

    for n in notes:
        text = f"{n.get('title','')}\n{n.get('desc','')}\n{' '.join(n.get('tags', []) or [])}"
        # ① 负面语义前置过滤
        if any(w in text for w in neg_words):
            continue
        note_has_price = note_has_level = note_has_cat = note_has_scene = False
        # ② 价格信号（正则 + 同句排除词，句界 = 。！？；换行，逗号不算）
        for sentence in re.split(r"[。！？；\n]", text):
            if any(w in sentence for w in exclude_words):
                continue  # 同句含排除词（"人均80元，限量供应"）→ 整句价格信号跳过
            sentence_prices: set[float] = set()
            for pat in price_patterns:
                for m in pat.finditer(sentence):
                    try:
                        val = m.group(1)
                        if val is None:
                            continue
                        fv = float(val)
                    except (IndexError, ValueError):
                        continue
                    if fv in sentence_prices:
                        continue  # 重叠 pattern 可能匹配到同一价格（如"人均80元"被两个 pattern 命中），句内去重
                    sentence_prices.add(fv)
                    price_hits.append(fv)
                    note_has_price = True
        # ③ 层级信号（首个出现位置决定主导层级）
        best_pos, best_level = None, None
        for level, kws in level_kw.items():
            for kw in kws:
                pos = text.find(kw)
                if pos != -1 and (best_pos is None or pos < best_pos):
                    best_pos, best_level = pos, level
        if best_level:
            level_counts[best_level] += 1
            note_has_level = True
        # ④ 品类 / 场景（可多命中）
        for cat, kws in cat_kw.items():
            if any(kw in text for kw in kws):
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
                note_has_cat = True
        for sc, kws in scene_kw.items():
            if any(kw in text for kw in kws):
                scene_counts[sc] = scene_counts.get(sc, 0) + 1
                note_has_scene = True
        if note_has_price or note_has_level or note_has_cat or note_has_scene:
            signal_notes += 1

    confidence = "high" if signal_notes >= min_signal else "low"
    total_level = sum(level_counts.values())
    level_distribution = {k: round(v / total_level, 4) for k, v in level_counts.items()} if total_level else {}
    dominant_level = max(level_distribution, key=level_distribution.get) if level_distribution else None

    avg_price_band = None
    if len(price_hits) >= 3:
        prices = sorted(price_hits)
        avg_price_band = [int(_percentile(prices, 25)), int(_percentile(prices, 75))]

    top_categories = [k for k, _ in sorted(cat_counts.items(), key=lambda x: -x[1])[:3]]
    top_scenes = [k for k, _ in sorted(scene_counts.items(), key=lambda x: -x[1])[:3]]

    merchant_tiers: list[str] = []
    if dominant_level:
        merchant_tiers = a_cfg["merchant_tier_map"].get(tier_name, {}).get(dominant_level, [])

    concentration = level_distribution.get(dominant_level, 0.0) if dominant_level else 0.0
    verticality_audience_score = _interpolate([(0.4, 0.0), (0.7, 100.0)], concentration) if concentration else 0.0

    return {
        "dominant_level": dominant_level,
        "level_distribution": level_distribution,
        "avg_price_band": avg_price_band,
        "top_categories": top_categories,
        "top_scenes": top_scenes,
        "merchant_tiers": merchant_tiers,
        "signal_notes": signal_notes,
        "confidence": confidence,
        "verticality_audience_score": round(verticality_audience_score, 1),
    }


def _industry_benchmarks(exposure_est: float, interaction_rate_pct: float, notes: list[dict], c_cfg: dict) -> dict:
    """行业公开基准旁证（仅展示，不参与打分）。"""
    ib = c_cfg["industry_benchmarks"]
    weighted_list = [_weighted(n["stats"]) for n in notes]
    med = statistics.median(weighted_list) if weighted_list else 0.0
    viral = sum(1 for w in weighted_list if med > 0 and w >= med * 3) / max(1, len(weighted_list))

    def _band(value, lo, hi):
        if value is None:
            return None
        if value < lo:
            return "偏低"
        if value <= hi:
            return "中位"
        return "偏高"

    def _cpe_band(cpe, ntype):
        if cpe is None:
            return None
        b = ib["cpe_bands"][ntype]
        if cpe < b["excellent"]:
            return "优秀"
        if cpe < b["good"]:
            return "不错"
        if cpe <= b["normal"]:
            return "常态"
        return "偏高"

    interaction_band = _band(interaction_rate_pct, ib["interaction_rate"][0] * 100, ib["interaction_rate"][1] * 100)
    viral_band = _band(viral * 100, ib["viral_ratio"][0] * 100, ib["viral_ratio"][1] * 100)
    roi_note = None
    if interaction_band == "偏低" or viral_band == "偏低":
        roi_note = "互动/爆文低于行业基准，预估 ROI 承压，投放需跟踪成交"
    elif interaction_band == "中位":
        roi_note = "互动位于行业中位，预估 ROI 接近 1.5 阈值，建议小规模试投"
    else:
        roi_note = "互动高于行业基准，预估 ROI 有望超过 1.5"

    return {
        "interaction_rate_pct": round(interaction_rate_pct, 1) if interaction_rate_pct is not None else None,
        "interaction_band": interaction_band,
        "viral_ratio_pct": round(viral * 100, 1),
        "viral_band": viral_band,
        "roi_note": roi_note,
    }


def _score_cost_effectiveness(
    notes: list[dict],
    follower_count: int,
    tier: dict,
    pgy_price: dict | None,
    pgy_meta: dict | None,
    authenticity: dict,
    cfg: dict,
) -> dict:
    """性价比（v1.12）：真实性闸门未过→0 分；无报价→降级；分差制合并 + 双口径建议报价。"""
    c_cfg = cfg["cost"]
    if not authenticity["passed"]:
        return {
            "score": 0, "confidence": "high",
            "detail": {"authenticity": "failed", "reason": "authenticity_failed", "authenticity_signals": authenticity["hits"]},
        }

    pic = float((pgy_price or {}).get("picture_price") or 0)
    vid = float((pgy_price or {}).get("video_price") or 0)
    lower = (pgy_price or {}).get("lower_price")
    if pic <= 0 and vid <= 0:
        return {"score": None, "confidence": "low", "detail": {"reason": "no_price", "authenticity_signals": authenticity["hits"]}}

    conf = "high" if len(notes) >= 10 else "medium"
    _cnt = max(1, len(notes))
    weighted = sum(_weighted(n["stats"]) for n in notes) / _cnt
    interaction_rate = weighted / max(1, follower_count)
    interaction_rate_pct = interaction_rate * 100
    min_healthy = float(tier.get("min_healthy") or 1.0)
    quality_q = min(1.0, interaction_rate_pct / min_healthy)

    read_rate = float(c_cfg["read_rates"][tier["tier_name"]])
    exposure_est = (pgy_meta or {}).get("read_mid") or (follower_count * read_rate)
    tier_name = tier["tier_name"]

    results: dict[str, dict | None] = {}
    for ntype, price, factor in (
        ("picture", pic, float(c_cfg["type_factor"]["picture"])),
        ("video", vid, float(c_cfg["type_factor"]["video"])),
    ):
        if price <= 0:
            results[ntype] = None
            continue
        cpm = price / (exposure_est / 1000) if exposure_est else None
        cpe = price / (exposure_est * interaction_rate) if exposure_est and interaction_rate else None
        anchor = float(c_cfg["price_anchors"][tier_name][ntype])
        fair = anchor * (0.4 + 0.6 * quality_q)
        ratio = price / fair if fair else 0.0
        price_score = _interpolate(c_cfg["points"], ratio)
        cap = 30 if quality_q < float(c_cfg["quality_hard_gate"]) else (50 if quality_q < float(c_cfg["quality_gate"]) else 100)
        price_score = min(price_score, cap)

        read_unit = float(c_cfg["read_unit"][tier_name])
        inter_unit = float(c_cfg["inter_unit"][tier_name])
        read_value = exposure_est / 1000 * read_unit
        inter_value = exposure_est * interaction_rate * inter_unit

        if quality_q >= float(c_cfg["quality_gate"]):
            discount = 0.5 + 0.5 * quality_q
            ceiling = max(read_value, inter_value) * discount * factor
            bid = (0.6 * inter_value + 0.4 * read_value) * discount * factor
        elif quality_q >= float(c_cfg["quality_hard_gate"]):
            discount = 0.5 * quality_q
            ceiling = max(read_value, inter_value) * discount * factor
            bid = (0.6 * inter_value + 0.4 * read_value) * discount * factor
        else:
            ceiling = bid = None

        bid_range = None
        if bid is not None:
            bid = bid * c_cfg["fusion"]["data"] + anchor * c_cfg["fusion"]["anchor"] * float(c_cfg["bid_merchant_discount"])
            ceiling = ceiling * c_cfg["fusion"]["data"] + anchor * c_cfg["fusion"]["anchor"]
            bid = round(bid)
            ceiling = round(ceiling)
            bid_range = [int(round(bid * c_cfg["range"][0])), int(round(bid * c_cfg["range"][1]))]

        lower_warning = None
        if lower and bid is not None and bid < float(lower):
            lower_warning = f"博主自报底价 {float(lower):.0f} 高于系统建议 {bid}，可能不接受该价位"

        results[ntype] = {
            "score": round(price_score, 1), "cpm": cpm, "cpe": cpe, "fair": round(fair, 1),
            "ratio": ratio, "suggested_bid": bid, "range": bid_range,
            "value_ceiling": ceiling, "lower_warning": lower_warning,
        }

    # 分差制合并（v1.9）
    scores = [r["score"] for r in results.values() if r]
    gap_flag = False
    if not scores:
        overall_score = None
    elif len(scores) == 1:
        overall_score = round(scores[0], 1)
    else:
        diff = abs(scores[0] - scores[1])
        if diff < 20:
            w_pic = float(c_cfg["type_factor"]["picture"])
            w_vid = float(c_cfg["type_factor"]["video"])
            overall_score = round((scores[0] * w_pic + scores[1] * w_vid) / (w_pic + w_vid), 1)
        else:
            overall_score = round(max(scores) * 0.85, 1)
            gap_flag = True

    industry = _industry_benchmarks(exposure_est, interaction_rate_pct, notes, c_cfg)

    audit = None
    cpm_platform = None
    click_mid = (pgy_meta or {}).get("click_mid")
    pic_res = results.get("picture")
    if click_mid and pic_res and pic_res.get("cpm"):
        cpm_platform = pic / (float(click_mid) / 1000)
        r = max(cpm_platform, pic_res["cpm"]) / max(1e-6, min(cpm_platform, pic_res["cpm"]))
        if r > float(c_cfg["cpm_mismatch"]["red"]):
            audit = "red"
        elif r > float(c_cfg["cpm_mismatch"]["yellow"]):
            audit = "yellow"

    def _g(ntype, field):
        r = results.get(ntype)
        return r.get(field) if r else None

    return {
        "score": overall_score,
        "confidence": conf,
        "detail": {
            "authenticity": "passed",
            "authenticity_signals": authenticity["hits"],
            "picture_price": pic, "video_price": vid, "lower_price": lower,
            "fair_picture": _g("picture", "fair"), "fair_video": _g("video", "fair"),
            "suggested_bid_picture": _g("picture", "suggested_bid"), "suggested_bid_video": _g("video", "suggested_bid"),
            "suggested_range_picture": _g("picture", "range"), "suggested_range_video": _g("video", "range"),
            "value_ceiling_picture": _g("picture", "value_ceiling"), "value_ceiling_video": _g("video", "value_ceiling"),
            "lower_price_warning": _g("picture", "lower_warning") or _g("video", "lower_warning"),
            "cpm": _g("picture", "cpm"), "cpe": _g("picture", "cpe"),
            "cpm_platform": round(cpm_platform, 2) if cpm_platform else None,
            "audit_flag": audit, "type_score_gap_flag": gap_flag,
            "quality_q": round(quality_q, 3),
            "price_ratio_picture": _g("picture", "ratio"),
            "anchor_tier": tier_name,
            "exposure_source": "pgy_read" if (pgy_meta or {}).get("read_mid") else "read_rate_est",
            "industry_benchmarks": industry,
        },
    }


def _audience_match(audience: dict, merchant_profile: dict | None, tier: dict, cfg: dict) -> dict:
    """商家目标层级匹配（v1.12）：客单价 0.40 / 品类 0.25 / 层级 0.25 / 城市 0.10，缺项权重重分配。"""
    a_cfg = cfg["audience"]
    if not merchant_profile:
        return {"has_profile": False, "score": None, "sub_scores": {}, "mismatches": []}
    threshold = float(a_cfg["match_threshold"])
    weights = {"price_overlap": 0.40, "category_overlap": 0.25, "level_match": 0.25, "city_match": 0.10}
    sub: dict[str, int] = {}

    band = audience.get("avg_price_band")
    target = merchant_profile.get("target_price_band")
    if band and target and len(target) == 2 and target[0] is not None and target[1] is not None:
        a1, a2 = float(band[0]), float(band[1])
        t1, t2 = float(target[0]), float(target[1])
        if t1 == t2:
            if a1 <= t1 <= a2:
                s = 100.0
            else:
                width = a2 - a1
                dist = min(abs(t1 - a1), abs(t1 - a2))
                s = max(0.0, (1 - dist / width) * 100) if width > 0 else 0.0
        else:
            overlap = max(0.0, min(a2, t2) - max(a1, t1))
            union = max(a2, t2) - min(a1, t1)
            s = overlap / union * 100 if union > 0 else 100.0
        sub["price_overlap"] = round(s)

    cats = set(audience.get("top_categories") or [])
    targets = set(merchant_profile.get("target_categories") or [])
    if targets:
        hit = len(cats & targets)
        sub["category_overlap"] = round(hit / len(targets) * 100)

    dl = audience.get("dominant_level")
    tl = merchant_profile.get("target_merchant_tier")
    if dl and tl:
        order = ["大众", "中端", "高端", "奢华"]
        if dl in order and tl in order:
            d = abs(order.index(dl) - order.index(tl))
            sub["level_match"] = 100 if d == 0 else (60 if d == 1 else (20 if d == 2 else 0))

    cs = merchant_profile.get("city_scope")
    expected = {"T1": ["本地"], "T2": ["区域"], "T3": ["区域", "全国"], "T4": ["全国"]}.get(tier["tier_name"], [])
    scope_order = ["本地", "区域", "全国"]
    if cs and expected:
        if cs in expected:
            s = 100.0
        else:
            dists = [abs(scope_order.index(cs) - scope_order.index(e)) for e in expected if e in scope_order]
            s = (60.0 if dists and min(dists) == 1 else 20.0) if dists else 0.0
        sub["city_match"] = round(s)

    denom = sum(w for k, w in weights.items() if k in sub)
    score = round(sum(sub[k] * weights[k] for k in sub) / denom) if denom else None
    mismatches: list[str] = []
    if score is not None and score < threshold:
        for k, s in sub.items():
            if s < threshold:
                mismatches.append(f"{k}={s}")
    return {"has_profile": True, "score": score, "sub_scores": sub, "mismatches": mismatches}
