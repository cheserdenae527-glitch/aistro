"""博主真实数据评分引擎（C9 设计方案实现）。

原则：只消费真实详情样本；缺失就是缺失，绝不估算、不外推。
结构：四维评分 + 粉丝分层归一化 + 类型内标准化 + 资格闸门（优先于分数）。
阈值：以下均为“结构占位”，需按 DESIGN-BLOGGER-SCORING-REALDATA.md §8 用真实账号标定后替换。
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

CN_TZ = timezone(timedelta(hours=8))

# 加权互动：点赞成本最低、最容易刷，权重最低；分享最难伪造，权重最高
LIKES_WEIGHT = 1
COLLECTS_WEIGHT = 4
COMMENTS_WEIGHT = 5
SHARES_WEIGHT = 6

# 粉丝分层（含互动质量映射阈值，百分数；分段间线性插值）
# 初版标定 2026-08-08（样本 T1=12 / T2=12 / T3=11 / T4=4），P10→0、P25→40、P50→70、P90→100，待人工复核
TIERS = {
    "T1": {"min": 1000, "max": 10000, "points": [(6.906, 0), (16.784, 40), (41.851, 70), (74.377, 100)], "min_healthy": 6.906},
    "T2": {"min": 10000, "max": 100000, "points": [(2.946, 0), (7.810, 40), (12.343, 70), (71.005, 100)], "min_healthy": 2.946},
    "T3": {"min": 100000, "max": 1000000, "points": [(1.161, 0), (2.210, 40), (5.202, 70), (13.548, 100)], "min_healthy": 1.161},
    "T4": {"min": 1000000, "max": None, "points": [(0.833, 0), (1.745, 40), (2.367, 70), (2.631, 100)], "min_healthy": 0.833},
}

DIMENSION_WEIGHTS = {
    "interaction_quality": 0.35,
    "content_stability": 0.30,
    "sustained_operation": 0.20,
    "trend": 0.15,
}

LEVELS = [
    (85, "卓越", "优先入选"),
    (70, "优秀", "推荐入选"),
    (55, "良好", "候选观察"),
    (40, "一般", "暂不推荐"),
    (0, "待观察", "过滤"),
]

ANALYSIS_WINDOW_DAYS = 90
TREND_MIN_SAMPLES = 10
STALE_DAYS = 60
VOTE_BAN_RATIO = 0.20
FAKE_RATIO_THRESHOLD = 0.005


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
    for tier in TIERS.values():
        if fans >= tier["min"] and (tier["max"] is None or fans < tier["max"]):
            return tier
    # 粉丝 <1000 的账号按 T1（尾部）口径评分，避免误落到 T4 顶部阈值
    return TIERS["T1"]


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


def _score_content_stability(std_values: list[float], notes: list[dict]) -> dict:
    if not notes:
        return {"score": 0.0, "quality_ratio": 0.0, "cv": 0.0}
    quality_count = sum(1 for v in std_values if v >= 200)
    ratio = quality_count / len(notes)
    ratio_score = _interpolate([(0.0, 0), (0.08, 40), (0.15, 70), (0.25, 100)], ratio)
    mean = statistics.fmean(std_values) if std_values else 0.0
    if mean > 0 and len(std_values) >= 2:
        cv = statistics.pstdev(std_values) / mean
    else:
        cv = 0.0
    stability_term = (1 - min(cv, 1.0)) * 100 if mean > 0 else 50.0
    score = ratio_score * 0.7 + stability_term * 0.3
    return {
        "score": round(score, 1),
        "quality_ratio": round(ratio * 100, 1),
        "cv": round(cv, 3),
    }


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


def score_blogger(
    notes: list[dict],
    follower_count: int = 0,
    total_notes: int = 0,
    now: datetime | None = None,
    sampled: bool = False,
    coverage_denominator: int | None = None,
) -> dict:
    """运行真实数据评分，返回可直接落库/展示的结果结构。"""
    now = now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)

    real = _real_notes(notes)
    fetched = len(real)
    sample_size = coverage_denominator if coverage_denominator is not None else total_notes
    coverage_rate = fetched / sample_size if sample_size else 0.0
    if coverage_rate >= 0.8 and fetched >= 30:
        confidence = "high"
    elif coverage_rate >= 0.5 and fetched >= 15:
        confidence = "medium"
    else:
        confidence = "low"

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
        "confidence": confidence,
        "dimensions": {},
        "overall": None,
        "anomalies": [],
        "insights": [],
        "timeline": _build_timeline(real),
        "notes": sorted(real, key=lambda n: n.get("published_at") or "", reverse=True),
    }

    if sampled and sample_size:
        base["insights"].append(f"抽样分析：共 {total_notes} 篇，均匀抽取 {sample_size} 篇真实详情")

    if confidence == "low":
        base["insights"].append("数据不足，暂不评分")
        return base

    tier = _tier_for(follower_count)
    std_values = _type_standardized(real)
    iq = _score_interaction_quality(real, follower_count, tier, now)
    stability = _score_content_stability(std_values, real)
    sustained = _score_sustained_operation(real, now)
    trend = _score_trend(std_values, real)

    dimensions = {
        "interaction_quality": {"score": iq["score"], "confidence": "high", "detail": {"rate_percent": iq["rate"], "sample": iq["sample"]}},
        "content_stability": {"score": stability["score"], "confidence": "high", "detail": {"quality_ratio": stability["quality_ratio"], "cv": stability["cv"]}},
        "sustained_operation": {"score": sustained["score"], "confidence": "high", "detail": {"weekly_notes": sustained["weekly_notes"], "freshness_days": sustained["freshness_days"]}},
    }
    weights = dict(DIMENSION_WEIGHTS)
    if trend["skipped"]:
        dimensions["trend"] = {"score": None, "confidence": "low", "detail": {"reason": trend["reason"]}}
        del weights["trend"]
        base["insights"].append(trend["reason"])
    else:
        dimensions["trend"] = {"score": trend["score"], "confidence": "high", "detail": {"ratio": trend["ratio"], "note": trend["note"]}}

    total_weight = sum(weights.values())
    overall = sum(dimensions[k]["score"] * weights[k] for k in weights if dimensions[k].get("score") is not None) / total_weight
    overall = round(overall, 1)
    level, desc = _level_for(overall)

    # 资格闸门（优先级：覆盖率→刷量→倒挂→停更）
    # 2. 刷量嫌疑
    likes = [int(n["stats"].get("liked", 0) or 0) for n in real]
    median_likes = statistics.median(likes) if likes else 0.0
    fake_hits = 0
    if median_likes > 0:
        for n in real:
            st = n["stats"]
            liked = int(st.get("liked", 0) or 0)
            extra = int(st.get("collected", 0) or 0) + int(st.get("comments", 0) or 0) + int(st.get("shared", 0) or 0)
            if liked >= median_likes * 3 and (extra / liked if liked else 0) < FAKE_RATIO_THRESHOLD:
                fake_hits += 1
    fake_ratio = fake_hits / len(real) if real else 0.0
    if fake_ratio > VOTE_BAN_RATIO:
        base["anomalies"].append({"type": "fake_engagement", "level": "block", "detail": "疑似刷量笔记占比过高"})
        base["overall"] = None
        base["insights"].append("疑似刷量，不建议合作")
        base["dimensions"] = dimensions
        base["result_forced"] = True
        return base

    # 3. 粉丝互动倒挂
    if iq["rate"] < tier["min_healthy"]:
        base["anomalies"].append({"type": "interaction_inversion", "level": "cap", "detail": "粉丝互动倒挂"})
        level = "待观察"
        desc = "粉丝互动倒挂，等级封顶待观察"

    # 4. 发布停滞
    if sustained["freshness_days"] is not None and sustained["freshness_days"] > STALE_DAYS:
        base["anomalies"].append({"type": "stale", "level": "downgrade", "detail": "最新笔记发布时间超过60天"})
        level = _downgrade_level(level)
        base["insights"].append("账号可能已停更")

    base["dimensions"] = dimensions
    base["overall"] = {"score": overall, "level": level, "description": desc}
    base["insights"].append(f"综合评分 {overall}，等级：{level}")
    return base
