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
