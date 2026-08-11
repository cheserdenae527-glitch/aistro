"""小红书博主数据分析评分引擎。

输入：标准化笔记列表（processor.normalize_note 输出，或前端传入的同构结构）+ 粉丝数。
输出：五维评分（互动质量/内容效能/活跃度/稳定性/趋势）、综合等级、周/月时间轴、排序笔记与洞察。

评分口径（小红书聚焦版）：
- 加权互动 = 点赞×1 + 收藏×1 + 评论×4 + 分享×4
- 互动质量：近30天加权互动 / 粉丝数
- 内容效能：加权互动 >= 均值3倍的笔记占比（爆文率）
- 活跃度：近30天周均发布数
- 稳定性：发布时间间隔变异系数 CV
- 趋势：近30天平均互动 / 前30天平均互动
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.blogger_scoring import (
    _build_decision,
    _score_grass_planting,
    _score_growth_potential,
    _summarize_follower_history,
    _tier_for,
)

CN_TZ = timezone(timedelta(hours=8))

DIMENSION_WEIGHTS = {
    "interaction_quality": 0.25,
    "content_effectiveness": 0.25,
    "activity": 0.15,
    "stability": 0.15,
    "trend": 0.20,
}

LEVELS = [
    (85, "卓越", "内容与账号运营处于头部水平，可持续放大优势"),
    (70, "优秀", "综合表现亮眼，稳定性和内容效能均在线"),
    (55, "良好", "基础扎实，仍有明确的提升空间"),
    (40, "一般", "内容产出与互动处于中等偏下，需要系统优化"),
    (0, "待观察", "数据基础薄弱，建议先稳定更新并观察反馈"),
]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        s = str(value).strip().replace(",", "").replace("+", "").replace("＋", "")
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
        if "千" in s:
            return int(float(s.replace("千", "")) * 1000)
        return int(float(s))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    """解析 XHS 常见时间格式：毫秒/秒时间戳或 ISO 字符串。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(CN_TZ)
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return None
        if ts <= 0:
            return None
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, CN_TZ)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CN_TZ)
            return dt.astimezone(CN_TZ)
        except ValueError:
            continue
    return None


def _published_at(note: dict) -> datetime | None:
    """从标准化笔记或其 raw 中尽力提取发布时间。"""
    for key in ("published_at", "created_at", "upload_time", "create_time", "last_update_time"):
        dt = _parse_datetime(note.get(key))
        if dt:
            return dt
    nc = note.get("note_card") if isinstance(note.get("note_card"), dict) else {}
    if nc:
        for key in ("time", "published_at", "create_time"):
            dt = _parse_datetime(nc.get(key))
            if dt:
                return dt
    raw = note.get("raw")
    if isinstance(raw, dict):
        return _published_at(raw)
    return None


def _stats(note: dict) -> dict:
    st = note.get("stats") or {}
    if not isinstance(st, dict):
        return {"liked": 0, "collected": 0, "comments": 0, "shared": 0}
    return {
        "liked": _to_int(st.get("liked", st.get("liked_count"))),
        "collected": _to_int(st.get("collected", st.get("collected_count"))),
        "comments": _to_int(st.get("comments", st.get("comment_count"))),
        "shared": _to_int(st.get("shared", st.get("shared_count"))),
    }


def _weighted_engagement(st: dict) -> int:
    return st["liked"] + st["collected"] + st["comments"] * 4 + st["shared"] * 4


def _plain_engagement(st: dict) -> int:
    return st["liked"] + st["collected"] + st["comments"] + st["shared"]


def _interpolate(points: list[tuple[float, float]], x: float) -> float:
    """分段线性插值，低于/高于边界时取端点值。"""
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


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _recent_notes(notes: list[dict], days: int, now: datetime) -> list[dict]:
    cutoff = now - timedelta(days=days)
    return [n for n in notes if n.get("published_at_dt") is not None and n["published_at_dt"] >= cutoff]


def _analysis_notes(notes: list[dict]) -> list[dict]:
    """评分样本优先取完整数据笔记；无完整数据时退化为列表数据。"""
    full = [n for n in notes if n.get("full_stats")]
    return full or notes


def _score_interaction_quality(notes: list[dict], fans: int, now: datetime) -> dict:
    notes = _analysis_notes(notes)
    recent = _recent_notes(notes, 30, now)
    recent_engagement = sum(n["weighted_engagement"] for n in recent)
    if fans <= 0:
        return {
            "score": 50.0,
            "detail": {
                "recent_notes": len(recent),
                "recent_weighted_engagement": recent_engagement,
                "fans": fans,
                "engagement_rate": None,
                "note": "粉丝数缺失，互动质量按中性分处理",
            },
        }
    rate = recent_engagement / fans * 100.0
    score = _interpolate([(0, 0), (1, 20), (3, 50), (5, 75), (8, 100)], rate)
    return {
        "score": _round(score),
        "detail": {
            "recent_notes": len(recent),
            "recent_weighted_engagement": recent_engagement,
            "fans": fans,
            "engagement_rate": _round(rate, 2),
            "note": "近30天加权互动 / 粉丝数，越高互动质量越好",
        },
    }


def _score_content_effectiveness(notes: list[dict]) -> dict:
    notes = _analysis_notes(notes)
    if len(notes) < 5:
        return {
            "score": 50.0,
            "detail": {
                "viral_count": 0,
                "viral_rate": None,
                "avg_weighted_engagement": _round(sum(n["weighted_engagement"] for n in notes) / max(len(notes), 1), 1),
                "note": "样本不足5条，内容效能按中性分处理",
            },
        }
    weights = [n["weighted_engagement"] for n in notes]
    avg = sum(weights) / len(weights)
    if avg <= 0:
        viral_count = 0
    else:
        viral_count = sum(1 for w in weights if w >= avg * 3)
    viral_rate = viral_count / len(notes)
    score = _interpolate([(0, 0), (0.05, 35), (0.10, 60), (0.20, 100)], viral_rate)
    return {
        "score": _round(score),
        "detail": {
            "viral_count": viral_count,
            "viral_rate": _round(viral_rate * 100, 1),
            "avg_weighted_engagement": _round(avg, 1),
            "threshold": _round(avg * 3, 1),
            "note": "爆文率 = 加权互动 >= 均值3倍的笔记占比",
        },
    }


def _score_activity(notes: list[dict], now: datetime) -> dict:
    notes = _analysis_notes(notes)
    recent = _recent_notes(notes, 30, now)
    if not recent:
        return {
            "score": 0.0,
            "detail": {"recent_30d_notes": 0, "weekly_notes": 0.0, "note": "近30天无发布"},
        }
    weekly = len(recent) / 4.345
    score = _interpolate([(0, 25), (0.5, 25), (1, 50), (2, 75), (3, 100)], weekly)
    return {
        "score": _round(score),
        "detail": {
            "recent_30d_notes": len(recent),
            "weekly_notes": _round(weekly, 2),
            "note": "近30天周均发布数，>=3 为高活跃",
        },
    }


def _score_stability(notes: list[dict]) -> dict:
    notes = _analysis_notes(notes)
    timed = sorted((n["published_at_dt"] for n in notes if n.get("published_at_dt") is not None))
    if len(timed) < 3:
        return {
            "score": 50.0,
            "detail": {"timed_notes": len(timed), "cv": None, "note": "有发布时间的样本不足3条，稳定性按中性分处理"},
        }
    gaps = [(timed[i] - timed[i - 1]).total_seconds() / 86400.0 for i in range(1, len(timed))]
    mean_gap = statistics.fmean(gaps)
    if mean_gap <= 0:
        cv = 0.0
    elif len(gaps) >= 2:
        cv = statistics.pstdev(gaps) / mean_gap
    else:
        cv = 0.0
    score = (1 - min(cv, 1.0)) * 100
    return {
        "score": _round(score),
        "detail": {
            "timed_notes": len(timed),
            "interval_days_mean": _round(mean_gap, 1),
            "cv": _round(cv, 3),
            "note": "间隔变异系数越低越稳定",
        },
    }


def _score_trend(notes: list[dict], now: datetime) -> dict:
    notes = _analysis_notes(notes)
    recent = _recent_notes(notes, 30, now)
    prev = [n for n in notes if n.get("published_at_dt") is not None and now - timedelta(days=60) <= n["published_at_dt"] < now - timedelta(days=30)]
    avg_recent = statistics.fmean([n["weighted_engagement"] for n in recent]) if recent else 0.0
    avg_prev = statistics.fmean([n["weighted_engagement"] for n in prev]) if prev else 0.0

    if len(recent) < 2 or len(prev) < 2:
        # 样本不足以支撑自然月窗口时，按篇数对半分：近半程 vs 前半程
        timed = sorted(
            (n for n in notes if n.get("published_at_dt") is not None),
            key=lambda n: n["published_at_dt"],
        )
        if len(timed) >= 4:
            mid = len(timed) // 2
            earlier = timed[:mid]
            later = timed[mid:]
            avg_earlier = statistics.fmean([n["weighted_engagement"] for n in earlier]) if earlier else 0.0
            avg_later = statistics.fmean([n["weighted_engagement"] for n in later]) if later else 0.0
            if avg_earlier <= 0:
                growth = None
                score = 60.0 if avg_later > 0 else 50.0
            else:
                growth = (avg_later - avg_earlier) / avg_earlier
                score = _interpolate([(-0.5, 20), (0, 60), (0.5, 100)], growth)
            return {
                "score": _round(score),
                "detail": {
                    "avg_recent": _round(avg_later, 1),
                    "avg_prev": _round(avg_earlier, 1),
                    "growth_ratio": _round(growth * 100, 1) if growth is not None else None,
                    "note": "样本不足以支撑自然月窗口，按近半程/前半程（篇数对半分）估算",
                },
            }

    if not recent and not prev:
        return {
            "score": 50.0,
            "detail": {"avg_recent": 0.0, "avg_prev": 0.0, "growth_ratio": None, "note": "近60天无数据，趋势按中性分处理"},
        }
    if avg_prev <= 0:
        growth = None
        score = 60.0 if avg_recent > 0 else 50.0
    else:
        growth = (avg_recent - avg_prev) / avg_prev
        score = _interpolate([(-0.5, 20), (0, 60), (0.5, 100)], growth)
    return {
        "score": _round(score),
        "detail": {
            "avg_recent": _round(avg_recent, 1),
            "avg_prev": _round(avg_prev, 1),
            "growth_ratio": _round(growth * 100, 1) if growth is not None else None,
            "note": "近30天平均互动 / 前30天平均互动的增长",
        },
    }


def _build_timeline(notes: list[dict]) -> dict:
    notes = _analysis_notes(notes)
    timed = [n for n in notes if n.get("published_at_dt") is not None]
    if not timed:
        return {"type": "weekly", "items": []}

    week_buckets: dict[str, dict] = {}
    month_buckets: dict[str, dict] = {}
    for n in timed:
        dt = n["published_at_dt"]
        wk = dt - timedelta(days=dt.weekday())
        wk_key = wk.date().isoformat()
        month_key = dt.strftime("%Y-%m")
        bucket = week_buckets.setdefault(wk_key, {"key": wk_key, "label": f"{wk.month}.{wk.day}", "notes": 0, "likes": 0, "comments": 0, "collects": 0, "shares": 0, "engagement": 0})
        mbucket = month_buckets.setdefault(month_key, {"key": month_key, "label": f"{dt.year}年{dt.month}月", "notes": 0, "likes": 0, "comments": 0, "collects": 0, "shares": 0, "engagement": 0})
        st = n["stats"]
        for b in (bucket, mbucket):
            b["notes"] += 1
            b["likes"] += st["liked"]
            b["comments"] += st["comments"]
            b["collects"] += st["collected"]
            b["shares"] += st["shared"]
            b["engagement"] += n["weighted_engagement"]

    if len(week_buckets) <= 104:
        weeks = sorted(week_buckets.values(), key=lambda b: b["key"])
        return {"type": "weekly", "items": weeks}

    months = sorted(month_buckets.values(), key=lambda b: b["key"])
    return {"type": "monthly", "items": months}


def _build_summary(notes: list[dict], fans: int, now: datetime, total_notes: int | None = None) -> dict:
    total_notes = total_notes or len(notes)
    detailed_notes = sum(1 for n in notes if n.get("full_stats"))
    scored = _analysis_notes(notes)
    stats_list = [n["stats"] for n in scored]

    def avg(key: str) -> float:
        return statistics.fmean([s[key] for s in stats_list]) if stats_list else 0.0

    total_engagement = sum(n["weighted_engagement"] for n in scored)
    avg_engagement = total_engagement / len(scored) if scored else 0.0
    engagement_values = [n["weighted_engagement"] for n in scored]
    median_engagement = statistics.median(engagement_values) if engagement_values else 0.0
    viral_count = sum(1 for n in scored if n["is_viral"])
    viral_rate = viral_count / len(scored) if scored else 0.0
    total_likes = sum(s["liked"] for s in stats_list)
    total_comments = sum(s["comments"] for s in stats_list)
    total_collects = sum(s["collected"] for s in stats_list)
    total_shares = sum(s["shared"] for s in stats_list)
    total_plain = max(total_likes + total_comments + total_collects + total_shares, 1)
    recent_30d_engagement = sum(n["weighted_engagement"] for n in _recent_notes(scored, 30, now))
    engagement_rate = recent_30d_engagement / fans * 100 if fans > 0 else None

    peak = max(scored, key=lambda n: n["weighted_engagement"]) if scored else None
    timed = [n for n in scored if n.get("published_at_dt") is not None]
    return {
        "total_notes": total_notes,
        "detailed_notes": detailed_notes,
        "partial_notes": total_notes - detailed_notes,
        "estimated_notes": sum(1 for n in notes if n.get("estimated")),
        "timed_notes": len(timed),
        "avg_likes": _round(avg("liked"), 1),
        "avg_comments": _round(avg("comments"), 1),
        "avg_collects": _round(avg("collected"), 1),
        "avg_shares": _round(avg("shared"), 1),
        "total_engagement": total_engagement,
        "avg_engagement": _round(avg_engagement, 1),
        "median_engagement": _round(median_engagement, 1),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_collects": total_collects,
        "total_shares": total_shares,
        "engagement_rate": _round(engagement_rate, 2) if engagement_rate is not None else None,
        "viral_count": viral_count,
        "viral_rate": _round(viral_rate * 100, 1),
        "like_collect_ratio": _round(total_likes / max(total_collects, 1), 2),
        "structure": {
            "likes": _round(total_likes / total_plain * 100, 1),
            "comments": _round(total_comments / total_plain * 100, 1),
            "collects": _round(total_collects / total_plain * 100, 1),
            "shares": _round(total_shares / total_plain * 100, 1),
        },
        "viral_peak": {
            "platform_note_id": peak["platform_note_id"],
            "title": peak.get("title", ""),
            "weighted_engagement": peak["weighted_engagement"],
            "published_at": peak["published_at_dt"].isoformat() if peak.get("published_at_dt") else None,
        } if peak else None,
    }


def _build_insights(dimensions: dict, summary: dict, overall_score: float, level: str) -> list[str]:
    insights: list[str] = []
    if summary.get("partial_notes", 0) > 0:
        insights.append(
            f"当前 {summary.get('detailed_notes', 0)} 篇为完整数据（含发布时间/评论/收藏），"
            f"另有 {summary.get('partial_notes', 0)} 篇仅有列表数据，评分与趋势基于完整数据样本。"
        )
    if summary.get("estimated_notes", 0) > 0:
        insights.append(
            f"其中 {summary.get('estimated_notes', 0)} 篇互动数据为按已抓详情比例估算值（estimated），"
            "精确数据请调高 detail_limit。"
        )
    iq = dimensions["interaction_quality"]
    rate = iq.get("detail", {}).get("engagement_rate")
    if rate is not None:
        insights.append(f"粉丝互动率 {rate}%，{'处于优秀水平' if rate >= 5 else '偏低，建议强化评论区运营和收藏钩子' if rate < 3 else '处于中等水平'}。")
    ce = dimensions["content_effectiveness"]
    vr = ce.get("detail", {}).get("viral_rate")
    if vr is not None:
        insights.append(f"爆文率 {vr}%，{'内容命中能力强' if vr >= 10 else '可参考头部爆文的选题与封面结构'}。")
    ac = dimensions["activity"]
    weekly = ac.get("detail", {}).get("weekly_notes")
    if weekly is not None:
        insights.append(f"近30天周均发布 {weekly} 篇，{'更新节奏充足' if weekly >= 2 else '建议提升更新频率以维持账号活跃'}。")
    st = dimensions["stability"]
    cv = st.get("detail", {}).get("cv")
    if cv is not None:
        insights.append(f"发布间隔变异系数 {cv}，{'节奏稳定' if cv < 0.4 else '发布节奏波动较大，建议固定更新日'}。")
    tr = dimensions["trend"]
    growth = tr.get("detail", {}).get("growth_ratio")
    if growth is not None:
        insights.append(f"近30天互动相对前30天{'增长' if growth > 0 else '下降'} {abs(growth)}%。")
    peak = summary.get("viral_peak")
    if peak:
        insights.append(f"最高互动笔记《{peak['title'][:20] or '无标题'}》加权互动 {peak['weighted_engagement']}，可拆解其选题、封面与正文结构。")
    insights.append(f"综合评分 {overall_score:.1f}，等级：{level}。")
    return insights


def analyze_notes(
    notes: list[dict],
    follower_count: int = 0,
    nickname: str = "",
    now: datetime | None = None,
    follower_history: list[dict] | None = None,
    total_notes: int | None = None,
) -> dict:
    """运行完整分析，返回可直出给前端的 JSON 结构。"""
    now = now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)
    enriched: list[dict] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        st = _stats(note)
        weighted = _weighted_engagement(st)
        dt = _published_at(note)
        enriched.append({
            **note,
            "stats": st,
            "engagement": _plain_engagement(st),
            "weighted_engagement": weighted,
            "published_at_dt": dt,
            "published_at": dt.isoformat() if dt else None,
            "full_stats": bool(note.get("full_stats")),
            "estimated": bool(note.get("estimated")),
            "is_viral": False,
        })
    scored_notes = _analysis_notes(enriched)
    avg_engagement = statistics.fmean([n["weighted_engagement"] for n in scored_notes]) if scored_notes else 0.0
    if avg_engagement > 0:
        for n in scored_notes:
            n["is_viral"] = n["weighted_engagement"] >= avg_engagement * 3

    dimensions = {
        "interaction_quality": _score_interaction_quality(enriched, follower_count, now),
        "content_effectiveness": _score_content_effectiveness(enriched),
        "activity": _score_activity(enriched, now),
        "stability": _score_stability(enriched),
        "trend": _score_trend(enriched, now),
    }
    for key in dimensions:
        dimensions[key]["confidence"] = "high"

    detailed_count = sum(1 for n in enriched if n.get("full_stats"))
    low_sample = detailed_count < 8
    if low_sample:
        for key in ("stability", "trend"):
            dimensions[key]["confidence"] = "low"
            base_note = (dimensions[key].get("detail") or {}).get("note") or ""
            dimensions[key]["detail"] = {
                **(dimensions[key].get("detail") or {}),
                "note": f"{base_note}样本不足，仅供参考".strip(),
            }

    weights = dict(DIMENSION_WEIGHTS)
    if low_sample:
        weights["stability"] *= 0.5
        weights["trend"] *= 0.5
    weight_total = sum(weights.values())
    overall = sum(dimensions[k]["score"] * weights[k] for k in weights) / weight_total
    overall = _round(overall, 1)
    level_label = "待观察"
    level_desc = LEVELS[-1][2]
    for threshold, label, desc in LEVELS:
        if overall >= threshold:
            level_label = label
            level_desc = desc
            break

    summary = _build_summary(enriched, follower_count, now, total_notes)
    timeline = _build_timeline(enriched)
    timed_notes = sorted((n for n in enriched if n.get("published_at_dt") is not None), key=lambda n: n["published_at_dt"], reverse=True)
    untimed_notes = [n for n in enriched if n.get("published_at_dt") is None]
    sorted_notes = timed_notes + untimed_notes
    insights = _build_insights(dimensions, summary, overall, level_label)
    grass = _score_grass_planting(enriched, follower_count, _tier_for(follower_count))
    growth = _score_growth_potential(enriched, follower_count, now, follower_history)

    return {
        "nickname": nickname,
        "follower_count": follower_count,
        "note_count": total_notes or len(enriched),
        "date_range": {
            "start": min((n["published_at_dt"] for n in enriched if n.get("published_at_dt")), default=None).isoformat() if any(n.get("published_at_dt") for n in enriched) else None,
            "end": max((n["published_at_dt"] for n in enriched if n.get("published_at_dt")), default=None).isoformat() if any(n.get("published_at_dt") for n in enriched) else None,
        },
        "summary": summary,
        "dimensions": dimensions,
        "overall": {"score": overall, "level": level_label, "description": level_desc},
        "timeline": timeline,
        "notes": sorted_notes,
        "insights": insights,
        "grass_planting": grass,
        "growth_potential": growth,
        "decision": _build_decision(grass, growth),
        "follower_history": _summarize_follower_history(follower_history),
    }
