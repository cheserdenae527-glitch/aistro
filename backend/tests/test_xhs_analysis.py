"""小红书博主分析评分引擎测试（纯逻辑，不需要数据库/网络）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services.xhs_analysis import analyze_notes

CN_TZ = __import__("app.services.xhs_analysis", fromlist=["CN_TZ"]).CN_TZ


def _mk_note(nid: str, ts: int, likes=100, collects=30, comments=5, shares=2, title="") -> dict:
    return {
        "platform_note_id": nid,
        "xsec_token": "t",
        "title": title or f"笔记-{nid}",
        "desc": "",
        "type": "normal",
        "cover_url": "",
        "image_urls": [],
        "author": {"id": "u1", "nickname": "测试博主", "avatar": ""},
        "stats": {"liked": likes, "collected": collects, "comments": comments, "shared": shares},
        "tags": [],
        "raw": {
            "note_card": {
                "time": ts,
                "display_title": title or f"笔记-{nid}",
                "interact_info": {
                    "liked_count": likes,
                    "collected_count": collects,
                    "comment_count": comments,
                    "shared_count": shares,
                },
            }
        },
    }


def _ts(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_high_quality_account_scores_high():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = []
    # 近30天：20 条高互动，其中 6 条为爆文
    for i in range(20):
        dt = now - timedelta(days=29) + timedelta(days=i * 1.5)
        likes = 5000 if i < 6 else 800
        collects = 1500 if i < 6 else 300
        comments = 300 if i < 6 else 60
        shares = 120 if i < 6 else 20
        notes.append(_mk_note(f"recent-{i}", _ts(dt), likes, collects, comments, shares))
    # 前30-60天：20 条低互动
    for i in range(20):
        dt = now - timedelta(days=59) + timedelta(days=i * 1.5)
        notes.append(_mk_note(f"prev-{i}", _ts(dt), 100, 50, 10, 5))

    res = analyze_notes(notes, follower_count=10000, nickname="高互动博主", now=now)
    assert res["note_count"] == 40
    assert res["overall"]["score"] >= 70
    assert res["dimensions"]["interaction_quality"]["score"] >= 80
    assert res["dimensions"]["activity"]["score"] >= 80
    assert res["dimensions"]["trend"]["score"] >= 80
    assert res["timeline"]["type"] == "weekly"
    assert len(res["timeline"]["items"]) > 8
    assert res["summary"]["viral_count"] >= 6


def test_empty_notes_does_not_crash():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    res = analyze_notes([], follower_count=5000, nickname="空账号", now=now)
    assert res["note_count"] == 0
    assert res["overall"]["level"] == "待观察"
    assert res["timeline"]["items"] == []
    assert res["notes"] == []


def test_untimed_notes_sorted_last():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    timed = _mk_note("timed", _ts(now - timedelta(days=1)), 100, 10, 2, 0, "有时间的")
    untimed = _mk_note("untimed", 0, 200, 20, 4, 0, "没时间的")
    untimed.pop("raw")
    res = analyze_notes([untimed, timed], follower_count=1000, nickname="排序测试", now=now)
    assert res["notes"][0]["platform_note_id"] == "timed"
    assert res["notes"][-1]["platform_note_id"] == "untimed"
    assert res["notes"][0]["published_at"] is not None
    assert res["notes"][-1]["published_at"] is None


def test_chinese_count_strings_parsed():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    note = _mk_note("cnt", _ts(now - timedelta(days=1)))
    note["stats"] = {"liked": "1.2万", "collected": "3千", "comments": 100, "shared": 10}
    res = analyze_notes([note], follower_count=10000, nickname="计数测试", now=now)
    # 1.2万 点赞 + 3千 收藏 + 评论100*4 + 分享10*4 = 12000 + 3000 + 400 + 40
    assert res["notes"][0]["weighted_engagement"] == 15440


def test_full_stats_sample_preferred():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = []
    for i in range(15):
        n = _mk_note(f"full-{i}", _ts(now - timedelta(days=i * 2)), 200 + i * 10, 50, 8, 3)
        n["full_stats"] = True
        notes.append(n)
    for i in range(5):
        n = _mk_note(f"partial-{i}", 0, 100)
        n["full_stats"] = False
        notes.append(n)
    res = analyze_notes(notes, follower_count=5000, nickname="混合数据", now=now)
    s = res["summary"]
    assert s["total_notes"] == 20
    assert s["detailed_notes"] == 15
    assert s["partial_notes"] == 5
    assert s["timed_notes"] == 15
    assert s["avg_comments"] == 8
    assert len(res["timeline"]["items"]) >= 5


# ===================== C8 抽样 / 估算 / 置信度 =====================


def _mk_full(nid, ts, likes, collects, comments, shares, estimated=False):
    n = _mk_note(nid, ts, likes, collects, comments, shares)
    n["full_stats"] = True
    n["estimated"] = estimated
    return n


def test_stratified_sample_covers_budget_and_median():
    from app.api.v1.notes import _build_stratified_sample, _note_likes

    notes = []
    for i in range(40):
        n = _mk_note(f"s{i}", 0, 100 + i * 10)
        notes.append(n)
    idx = _build_stratified_sample(notes, 6)
    assert len(idx) == 6
    sampled_likes = sorted(_note_likes(notes[i]) for i in idx)
    med = sorted(_note_likes(n) for n in notes)[len(notes) // 2]
    # 中位数区间必须被覆盖（保底逻辑）
    assert any(abs(liked - med) <= 100 for liked in sampled_likes)
    # 必须包含点赞最高的笔记
    assert max(sampled_likes) == _note_likes(max(notes, key=lambda n: _note_likes(n)))


def test_estimate_unfetched_stats_uses_ratios():
    from app.api.v1.notes import _estimate_unfetched_stats

    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [
        _mk_full("d1", now - timedelta(days=1), 1000, 100, 50, 10),
        _mk_full("d2", now - timedelta(days=2), 2000, 200, 100, 20),
        _mk_note("p1", 0, 1000),
    ]
    _estimate_unfetched_stats(notes)
    est = notes[-1]
    assert est.get("estimated") is True
    # 评论/点赞比例 = 150/3000 = 0.05 -> 1000 * 0.05 = 50
    assert est["stats"]["comments"] == 50
    assert est["stats"]["collected"] == 100


def test_low_sample_confidence_downweights():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk_full(f"f{i}", now - timedelta(days=i * 3), 500, 100, 20, 5) for i in range(4)]
    res = analyze_notes(notes, follower_count=5000, nickname="低样本", now=now)
    dims = res["dimensions"]
    assert dims["stability"]["confidence"] == "low"
    assert dims["trend"]["confidence"] == "low"
    assert res["summary"]["estimated_notes"] == 0


def test_trend_fallback_near_half_split():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = []
    for i in range(6):
        ts = now - timedelta(days=80 - i * 12)
        likes = 200 if i < 3 else 800
        notes.append(_mk_full(f"t{i}", ts, likes, 50, 10, 2))
    res = analyze_notes(notes, follower_count=5000, nickname="趋势回退", now=now)
    trend = res["dimensions"]["trend"]
    assert "近半程/前半程" in trend["detail"]["note"]


def test_estimated_flag_in_summary():
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=CN_TZ)
    notes = [
        _mk_full("d1", now - timedelta(days=1), 500, 100, 20, 5),
        _mk_note("p1", 0, 200),
    ]
    notes[-1]["estimated"] = True
    res = analyze_notes(notes, follower_count=5000, nickname="估算", now=now)
    assert res["summary"]["estimated_notes"] == 1
    assert any("估算" in t or "estimated" in t for t in res["insights"])
