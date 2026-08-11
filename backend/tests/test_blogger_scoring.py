"""博主真实数据评分引擎测试（C9）。"""
from __future__ import annotations

from datetime import datetime, timedelta

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
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["confidence"] == "high"
    assert res["overall"] is not None
    assert res["overall"]["score"] >= 70
    assert res["anomalies"] == []


def test_fake_engagement_blocks():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 1000, 300, 80, 40) for i in range(40)]
    for i in range(15):
        notes[i]["stats"] = {"liked": 100000, "collected": 0, "comments": 0, "shared": 0}
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["overall"] is None
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
    assert res["decision"]["status"] == "ok"
    assert res["decision"]["quadrant"] in ("首选合作", "短期投放", "潜力股", "过滤")


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
    assert res["decision"]["status"] == "no_data"


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
