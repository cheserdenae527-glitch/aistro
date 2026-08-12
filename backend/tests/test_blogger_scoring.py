"""博主真实数据评分引擎测试（C9）。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.blogger_scoring import score_blogger, CN_TZ


def _mk(i: int, dt: datetime, likes, collects, comments, shares, typ="normal") -> dict:
    return {
        "platform_note_id": f"n{i}",
        "type": typ,
        "stats": {"liked": likes, "collected": collects, "comments": comments, "shared": shares},
        "published_at": dt.isoformat(),
    }


def test_high_quality_account():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 900, 240, 120) for i in range(40)]
    for i in range(8):
        notes[i]["stats"] = {"liked": 12000, "collected": 3600, "comments": 960, "shared": 480}
    for n in notes:
        n["tags"] = ["探店", "美食"]
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now, follower_history=history)
    assert res["confidence"] == "high"
    assert res["overall"] is not None
    assert res["overall"]["score"] >= 70
    assert res["stage"]["label"] in ("成长", "成熟")
    assert res["decision"]["recommendation"] == "priority"
    assert set(res["dimensions"].keys()) == {
        "seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend",
        "cost_effectiveness",
    }
    assert res["anomalies"] == []


def test_fake_engagement_blocks():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 1000, 300, 80, 40) for i in range(40)]
    for i in range(15):
        notes[i]["stats"] = {"liked": 100000, "collected": 0, "comments": 0, "shared": 0}
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["overall"] is None
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "not_recommended"
    assert res["decision"]["low_quality"] is True
    assert any(a["type"] == "fake_engagement" and a["level"] == "block" for a in res["anomalies"])
    assert "疑似刷量" in res["insights"][-1]


def test_stale_downgrades():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=70 + i * 2), 3000, 900, 240, 120) for i in range(20)]
    res = score_blogger(notes, follower_count=50000, total_notes=20, now=now)
    assert any(a["type"] == "stale" for a in res["anomalies"])
    # 停更 + 无近90天数据，等级应被压到一般/待观察
    assert res["overall"]["level"] in ("一般", "待观察")


def test_low_coverage_no_score():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 1000, 300, 80, 40) for i in range(5)]
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["confidence"] == "low"
    assert res["overall"] is None
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "insufficient_data"


def test_trend_skipped_for_small_sample():
    from app.services.blogger_scoring import _score_trend, _type_standardized

    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 5), 1000, 300, 80, 40) for i in range(9)]
    std = _type_standardized(notes)
    trend = _score_trend(std, notes)
    assert trend["skipped"] is True
    assert "样本不足10篇" in trend["reason"]


def test_grass_growth_scores_present():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 240, 600) for i in range(30)]
    for n in notes:
        n["tags"] = ["探店", "美食"]
    res = score_blogger(notes, follower_count=50000, total_notes=30, now=now)
    assert res["grass_planting"]["score"] is not None
    assert res["growth_potential"]["score"] is not None
    assert res["decision"]["recommendation"] in ("priority", "ok", "caution")


def test_growth_renormalizes_without_follower_history():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 240, 600) for i in range(30)]
    res = score_blogger(notes, follower_count=50000, total_notes=30, now=now)
    gp = res["growth_potential"]
    assert gp["score"] is not None
    assert gp["components"]["follower_growth"]["score"] is None
    assert "暂无粉丝历史快照" in gp["components"]["follower_growth"]["detail"]["note"]


def test_low_coverage_decision_no_data():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 1000, 300, 80, 40) for i in range(5)]
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["decision"]["recommendation"] == "insufficient_data"
    assert res["decision"]["low_quality"] is False


def test_follower_growth_detected_from_history():
    from app.services.blogger_scoring import _score_follower_growth
    history = [
        {"fans": 10000, "snapshot_at": "2026-07-01T00:00:00+08:00"},
        {"fans": 13000, "snapshot_at": "2026-08-01T00:00:00+08:00"},
    ]
    score = _score_follower_growth(history)
    assert score is not None
    assert score >= 70
    assert _score_follower_growth([{"fans": 10000, "snapshot_at": "2026-07-01T00:00:00+08:00"}]) is None


def test_platform_follower_history_summary_and_detail():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 240, 600) for i in range(30)]
    history = [
        {"fans": 10000, "snapshot_at": "2026-07-01T00:00:00+08:00", "source": "justoneapi"},
        {"fans": 13000, "snapshot_at": "2026-08-01T00:00:00+08:00", "source": "justoneapi"},
    ]
    res = score_blogger(notes, follower_count=50000, total_notes=30, now=now, follower_history=history)
    assert res["follower_history"]["source"] == "justoneapi"
    assert res["follower_history"]["points"] == 2
    assert res["follower_history"]["growth_rate"] == 0.3
    assert len(res["follower_history"]["series"]) == 2
    fg = res["growth_potential"]["components"]["follower_growth"]
    assert fg["score"] is not None
    assert fg["detail"]["source"] == "justoneapi"
    assert fg["detail"]["growth_rate"] == 0.3


def test_seeding_depth_weights_and_detail():
    from app.services.blogger_scoring import _score_seeding_depth, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    res = _score_seeding_depth(notes, fans=50000, tier=_tier_for(50000), now=now)
    assert 0 <= res["score"] <= 100
    d = res["detail"]
    assert d["collect_like_ratio"] > 0.5  # 藏/赞 > 0.5，干货结构
    assert d["comment_signal_low_conf"] is True  # 默认未开评论分析


def test_seeding_depth_comment_reweight():
    from app.services.blogger_scoring import _score_seeding_depth, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    base = _score_seeding_depth(notes, fans=50000, tier=_tier_for(50000), now=now)
    with_comments = _score_seeding_depth(
        notes, fans=50000, tier=_tier_for(50000), now=now,
        comment_analysis={"intent_ratio": 0.3, "spam_ratio": 0.05},
    )
    assert with_comments["detail"]["comment_signal_low_conf"] is False
    assert with_comments["score"] != base["score"]


def test_seeding_depth_comment_detail_ratios():
    from app.services.blogger_scoring import _score_seeding_depth, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    res = _score_seeding_depth(
        notes, fans=50000, tier=_tier_for(50000), now=now,
        comment_analysis={"intent_ratio": 0.6, "spam_ratio": 0.2, "negative_ratio": 0.1, "sample": 50},
    )
    d = res["detail"]
    assert d["intent_ratio"] == 0.6
    assert d["spam_ratio"] == 0.2
    assert d["negative_ratio"] == 0.1
    assert d["comment_sample"] == 50
    assert d["comment_signal_low_conf"] is False
    # 默认未开启评论分析时，不暴露评论占比字段
    base = _score_seeding_depth(notes, fans=50000, tier=_tier_for(50000), now=now)
    assert "intent_ratio" not in base["detail"]


def test_comment_participation_mapping_ascending():
    from app.services.blogger_scoring import _comment_participation, _map_comment_participation

    # 映射锚点必须与 _interpolate 的升序约定一致：0→0、0.08→40、0.15→70、≥0.25→100
    assert _map_comment_participation(0.0) == 0
    assert _map_comment_participation(0.08) == 40
    assert _map_comment_participation(0.15) == 70
    assert _map_comment_participation(0.3) == 100
    assert 40 < _map_comment_participation(0.10) < 70
    # 互动全 0 的笔记不参与分子分母，参与度回退 0
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i), 0, 0, 0, 0) for i in range(5)]
    assert _comment_participation(notes) == 0.0


def test_tier_for_carries_tier_name():
    from app.services.blogger_scoring import _tier_for

    assert _tier_for(2000)["tier_name"] == "T1"
    assert _tier_for(50000)["tier_name"] == "T2"
    assert _tier_for(500000)["tier_name"] == "T3"
    assert _tier_for(2_000_000)["tier_name"] == "T4"


def test_grass_planting_uses_merged_tier_not_identity():
    # 回归：_tier_for 返回合并副本后，草评分层必须读 tier_name 而非对象身份。
    # 同粉丝、同笔记、仅分层不同：身份匹配回归会让两者都误落 T1 而得分相等。
    from app.services.blogger_scoring import _score_grass_planting, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    fans = 2_000_000
    t4 = _score_grass_planting(notes, fans=fans, tier=_tier_for(fans))
    t1 = _score_grass_planting(notes, fans=fans, tier=_tier_for(2000))
    assert t4["score"] is not None and t1["score"] is not None
    assert t4["score"] != t1["score"]


def test_stable_output_median_viral_and_no_cv_penalty():
    from app.services.blogger_scoring import _score_stable_output

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 20 篇普通 + 6 篇爆款（互动量 >> 中位数×3），正常账号高方差但连续发布
    notes = [_mk(i, now - timedelta(days=i * 2), 800, 300, 100, 50) for i in range(20)]
    for i in range(6):
        notes[i] = _mk(i, now - timedelta(days=i * 2), 9000, 3600, 900, 600)
    res = _score_stable_output(notes, now=now)
    # 中位数×3 阈值下 6/26 ≈ 23% 命中爆文 → 高分；连续发布无空白期 → 无稳健性扣分
    assert res["score"] >= 70
    assert res["detail"]["cliff_detected"] is False
    assert res["detail"]["gap_days"] == 0


def test_stable_output_gap_and_cliff_penalize():
    from app.services.blogger_scoring import _score_stable_output

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 近 30 天只有 1 篇（前 60 天密集），且前段互动高、后段骤降
    old = [_mk(i, now - timedelta(days=70 - i * 2), 5000, 1800, 500, 300) for i in range(15)]
    new = [_mk(99, now - timedelta(days=20), 300, 100, 30, 10)]
    res = _score_stable_output(old + new, now=now)
    assert res["detail"]["gap_days"] >= 14
    assert res["detail"]["cliff_detected"] is True
    assert res["score"] < 60


def test_stable_output_cliff_only():
    from app.services.blogger_scoring import _score_stable_output

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    older = [_mk(i, now - timedelta(days=35 + i * 2), 9000, 3600, 900, 600) for i in range(15)]  # 35..63 天前，高互动
    recent = [_mk(100 + i, now - timedelta(days=i * 2), 300, 100, 30, 10) for i in range(15)]     # 0..28 天前，低互动
    res = _score_stable_output(older + recent, now=now)
    assert res["detail"]["cliff_detected"] is True
    assert res["detail"]["gap_days"] == 0  # 无 ≥14 天空白期


def test_growth_trend_with_snapshot():
    from app.services.blogger_scoring import _score_growth_trend, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _score_growth_trend(notes, fans=50000, now=now, follower_history=history, tier=_tier_for(50000))
    # 快照间隔 30 天：月化涨粉率 (50000-45000)/45000 = 11.1%；/T2 基准 9% = 1.23 → 涨粉分封顶 100；复合 = 100×0.7 + 内容趋势60×0.3 = 88
    assert res["detail"]["has_snapshot"] is True
    assert res["detail"]["growth_rate"] == pytest.approx(0.1111, abs=1e-4)
    assert res["score"] == pytest.approx(88.0)
    assert res["confidence"] == "high"


def test_growth_trend_no_snapshot_low_conf():
    from app.services.blogger_scoring import _score_growth_trend, _score_trend, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    res = _score_growth_trend(notes, fans=50000, now=now, follower_history=None, tier=_tier_for(50000))
    assert res["detail"]["has_snapshot"] is False
    assert res["detail"]["weight_halved"] is True
    assert res["confidence"] == "low"
    # 无快照时仅按内容趋势计分：score 应等于 _score_trend 的原始分数
    assert res["score"] == _score_trend(None, notes)["score"]


@pytest.mark.parametrize(
    "history",
    [
        [{"fans": 10000, "snapshot_at": "2026-08-01T00:00:00+08:00"}],  # 仅一条快照
        [  # 间隔 >60 天 → 不月化
            {"fans": 10000, "snapshot_at": "2026-05-01T00:00:00+08:00"},
            {"fans": 13000, "snapshot_at": "2026-08-01T00:00:00+08:00"},
        ],
        [  # 前一快照 fans=0 → 过滤后不足两条有效快照
            {"fans": 0, "snapshot_at": "2026-07-01T00:00:00+08:00"},
            {"fans": 13000, "snapshot_at": "2026-08-01T00:00:00+08:00"},
        ],
    ],
)
def test_latest_growth_rate_edges(history):
    from app.services.blogger_scoring import _latest_growth_rate

    assert _latest_growth_rate(history) is None


def test_latest_growth_rate_monthlyizes():
    from app.services.blogger_scoring import _latest_growth_rate

    # 15 天涨 5% → 月化 ×2 = 10%
    history = [
        {"fans": 10000, "snapshot_at": "2026-07-17T00:00:00+08:00"},
        {"fans": 10500, "snapshot_at": "2026-08-01T00:00:00+08:00"},
    ]
    assert _latest_growth_rate(history) == pytest.approx(0.10)

def test_classify_stage_with_snapshot_growth():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _classify_stage(fans=50000, notes=notes, now=now, follower_history=history)
    assert res["label"] == "成长"
    assert res["confidence"] == "high"


def test_classify_stage_no_snapshot_low_conf():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    res = _classify_stage(fans=2000, notes=notes, now=now, follower_history=None)
    assert res["confidence"] == "low"
    assert res["label"] == "冷启动"  # 粉丝 < 5000


def test_classify_stage_decline():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 最新笔记 80 天前 → 停更倾向
    notes = [_mk(i, now - timedelta(days=80 + i * 2), 3000, 1200, 300, 200) for i in range(10)]
    history = [
        {"snapshot_at": (now - timedelta(days=40)).isoformat(), "fans": 52000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _classify_stage(fans=50000, notes=notes, now=now, follower_history=history)
    assert res["label"] == "衰退"
    assert res["confidence"] == "medium"

def test_classify_stage_stale_overrides_growth():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=80 + i * 2), 3000, 1200, 300, 200) for i in range(10)]  # 最新 80 天前
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _classify_stage(fans=50000, notes=notes, now=now, follower_history=history)
    assert res["label"] == "衰退"          # 有强正增长，但停更覆盖
    assert res["confidence"] == "medium"
    assert any("停更" in e for e in res["evidence"])


def test_classify_stage_no_snapshot_large_inactive_is_mature():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 大号、低频但未停更（无快照）：应为存量成熟，而非冷启动
    notes = [_mk(i, now - timedelta(days=40 + i * 20), 3000, 1200, 300, 200) for i in range(5)]  # 40..120 天前
    res = _classify_stage(fans=200000, notes=notes, now=now, follower_history=None)
    assert res["label"] == "成熟"
    assert res["confidence"] == "low"
    assert any("无有效涨粉快照" in e for e in res["evidence"])

def test_growth_anomaly_requires_both_conditions():
    from app.services.blogger_scoring import _growth_anomaly

    # 且关系：T2 标准阈值 20%，涨粉 25%（超阈值）但互动率未下降 → 不触发
    assert _growth_anomaly(growth_rate=0.25, interaction_drop=0.05, fans=50000) is None
    # 涨粉 25%（超阈值）且互动率下降 30% → 触发
    flag = _growth_anomaly(growth_rate=0.25, interaction_drop=0.30, fans=50000)
    assert flag is not None and flag["type"] == "growth_anomaly"
    # T1 小账号放大阈值：涨粉 25%（<35%）即使互动率下降也不触发
    assert _growth_anomaly(growth_rate=0.25, interaction_drop=0.30, fans=2000) is None


def test_collect_like_inversion_hit():
    from app.services.blogger_scoring import _collect_like_inversion_hit, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 高赞低藏：赞藏比中位数 0.01 < 0.2，且篇均收藏/粉丝 0.1% < T2 最低健康线 0.6% → True
    bad = [_mk(i, now - timedelta(days=i * 2), 5000, 50, 10, 2) for i in range(40)]
    assert _collect_like_inversion_hit(bad, fans=50000, tier=_tier_for(50000)) is True
    # 正常：赞藏比 0.53 ≥ 0.2 → False
    good = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    assert _collect_like_inversion_hit(good, fans=50000, tier=_tier_for(50000)) is False


def test_overall_confidence_single_noncore_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 80.0, "confidence": "high"},
        "verticality": {"score": 85.0, "confidence": "high"},
        "stable_output": {"score": 70.0, "confidence": "high"},
        "sustained_operation": {"score": 75.0, "confidence": "high"},
        "growth_trend": {"score": 60.0, "confidence": "low"},  # 单个非核心维度 low
    }
    assert _overall_confidence(dims, coverage_conf="high") == "medium"


def test_overall_confidence_seeding_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 30.0, "confidence": "low"},
        "verticality": {"score": 85.0, "confidence": "high"},
        "stable_output": {"score": 70.0, "confidence": "high"},
        "sustained_operation": {"score": 75.0, "confidence": "high"},
        "growth_trend": {"score": 80.0, "confidence": "high"},
    }
    assert _overall_confidence(dims, coverage_conf="high") == "low"


def test_overall_confidence_two_noncore_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 80.0, "confidence": "high"},
        "verticality": {"score": 45.0, "confidence": "low"},
        "stable_output": {"score": 70.0, "confidence": "high"},
        "sustained_operation": {"score": 75.0, "confidence": "high"},
        "growth_trend": {"score": 40.0, "confidence": "low"},
    }
    assert _overall_confidence(dims, coverage_conf="high") == "low"


def test_overall_confidence_coverage_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 80.0, "confidence": "high"},
        "verticality": {"score": 85.0, "confidence": "high"},
        "stable_output": {"score": 70.0, "confidence": "high"},
        "sustained_operation": {"score": 75.0, "confidence": "high"},
        "growth_trend": {"score": 80.0, "confidence": "high"},
    }
    # 覆盖率 low 由闸门 1 兜底：即使五维全 high 也取 low
    assert _overall_confidence(dims, coverage_conf="low") == "low"


def test_overall_confidence_skipped_noncore_not_counted():
    # v1.12：score=None（未评分/无数据）维度不参与置信度汇总，不把整体拖成 low
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 85.0, "confidence": "high"},
        "verticality": {"score": 80.0, "confidence": "high"},
        "stable_output": {"score": 75.0, "confidence": "high"},
        "sustained_operation": {"score": 70.0, "confidence": "high"},
        "growth_trend": {"score": None, "confidence": "low"},  # 无数据（无快照且内容趋势不足）
        "cost_effectiveness": {"score": None, "confidence": "low"},  # 无报价
    }
    assert _overall_confidence(dims, coverage_conf="high") == "high"


def test_overall_confidence_low_with_score_still_counts():
    # 有分数但置信度低（如无快照的 growth_trend）→ 仍计入 low
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 85.0, "confidence": "high"},
        "verticality": {"score": 80.0, "confidence": "high"},
        "stable_output": {"score": 75.0, "confidence": "high"},
        "sustained_operation": {"score": 70.0, "confidence": "high"},
        "growth_trend": {"score": 75.0, "confidence": "low"},  # 有分数但低置信
    }
    assert _overall_confidence(dims, coverage_conf="high") == "medium"


def test_overall_confidence_missing_confidence_key_fail_safe_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"score": 85.0, "confidence": "high"},
        "verticality": {"score": 80.0},  # 缺 confidence 键 → 按 low
        "stable_output": {"score": 75.0, "confidence": "high"},
        "sustained_operation": {"score": 70.0, "confidence": "high"},
        "growth_trend": {"score": 75.0, "confidence": "high"},
    }
    assert _overall_confidence(dims, coverage_conf="high") == "medium"


def test_overall_confidence_missing_seeding_depth_no_crash():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "verticality": {"score": 80.0, "confidence": "low"},
        "stable_output": {"score": 75.0, "confidence": "high"},
        "sustained_operation": {"score": 70.0, "confidence": "high"},
        "growth_trend": {"score": 75.0, "confidence": "high"},
    }
    # 缺 seeding_depth：不抛 KeyError，且因非核心单 low 且无 seeding_depth（视为非 low）→ medium
    assert _overall_confidence(dims, coverage_conf="high") == "medium"


def test_gate_collect_like_inversion_blocks():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 高赞低藏：赞藏比中位数 < 0.2，且篇均收藏/粉丝极低 → 刷量嫌疑闸门
    notes = [_mk(i, now - timedelta(days=i * 2), 5000, 50, 10, 2) for i in range(40)]
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["overall"] is None
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "not_recommended"
    assert any(a["type"] == "fake_engagement" and a["level"] == "block" for a in res["anomalies"])


def test_fake_engagement_spam_comment_flag_blocks():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 互动结构正常，仅水评占比超阈值触发闸门 2
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(40)]
    for n in notes:
        n["tags"] = ["探店", "美食"]
    res = score_blogger(
        notes, follower_count=50000, total_notes=40, now=now,
        comment_analysis={"intent_ratio": 0.1, "spam_ratio": 0.9, "negative_ratio": 0.0, "sample": 100},
    )
    assert res["overall"] is None
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "not_recommended"
    assert any(a["type"] == "fake_engagement" and a["detail"] == "疑似刷量（水评占比过高）" for a in res["anomalies"])
    assert res["decision"]["reasons"] == ["评论区水评占比过高"]


def test_growth_trend_no_snapshot_overall_medium():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 无快照 → growth_trend confidence low（非 None），单非核心 low → 整体 medium
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    for n in notes:
        n["tags"] = ["探店", "美食"]
    res = score_blogger(notes, follower_count=50000, total_notes=30, now=now, follower_history=None)
    assert res["confidence"] == "medium"
    assert res["dimensions"]["growth_trend"]["confidence"] == "low"


def test_no_interaction_inversion_when_fans_unknown():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    for n in notes:
        n["tags"] = ["探店", "美食"]
    res = score_blogger(notes, follower_count=0, total_notes=30, now=now)
    assert not any(a["type"] == "interaction_inversion" for a in res["anomalies"])
    assert res["overall"] is not None
    assert res["overall"]["level"] not in ("待观察",)
