"""Task C1：旧版博主分析结果回填脚本 — 纯函数单测（不连数据库）。

只测 scripts/backfill_blogger_analysis.py 里的纯函数：
- is_old_format：旧四维 dims 判定
- recompute_result：旧 result 重算为新的五维 result
用 SimpleNamespace 假 task 避免 DB。
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from backfill_blogger_analysis import is_old_format, recompute_result  # noqa: E402

CN_TZ = timezone(timedelta(hours=8))
NEW_DIMS = {"seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend"}
OLD_DIMS = {"trend", "content_stability", "interaction_quality", "sustained_operation"}


def _mk_note(i: int, dt: datetime, likes, collects, comments, shares, nickname="测试博主") -> dict:
    return {
        "platform_note_id": f"n{i}",
        "type": "normal",
        "author": {"nickname": nickname},
        "stats": {"liked": likes, "collected": collects, "comments": comments, "shared": shares},
        "published_at": dt.isoformat(),
    }


def _synthetic_notes(n: int = 30, nickname="测试博主") -> list[dict]:
    now = datetime.now(CN_TZ)
    return [_mk_note(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200, nickname=nickname) for i in range(n)]


def _old_result(notes: list[dict], follower_history=None, sampled=True, nickname="测试博主") -> dict:
    return {
        "dimensions": {k: {"score": 60, "confidence": "medium"} for k in OLD_DIMS},
        "stage": None,
        "overall": {"score": 57.0, "level": "良好", "description": "候选观察"},
        "notes": notes,
        "coverage": {"total_notes": 30, "sample_size": 30, "fetched_notes": 30},
        "sampled": sampled,
        "follower_history": follower_history,
        "nickname": nickname,
    }


def _task(result: dict, follower_count=50000, total_notes=30) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        xhs_user_id="xhs_test_001",
        follower_count=follower_count,
        total_notes=total_notes,
        status="success",
        result=result,
    )


# ---------- is_old_format ----------

def test_is_old_format_true_for_legacy_dimensions():
    assert is_old_format(_old_result(_synthetic_notes()))


def test_is_old_format_true_without_stage():
    result = _old_result(_synthetic_notes())
    result["stage"] = None
    assert is_old_format(result)


def test_is_old_format_false_for_new_five_dimensions():
    result = _old_result(_synthetic_notes())
    result["dimensions"] = {k: {"score": 60} for k in NEW_DIMS}
    assert not is_old_format(result)


def test_is_old_format_true_when_no_dimensions():
    assert is_old_format({})
    assert is_old_format({"dimensions": None})
    assert is_old_format({"dimensions": "not-a-dict"})


def test_is_old_format_true_when_dimensions_empty():
    assert is_old_format({"dimensions": {}})


def test_is_old_format_false_when_new_decision_present():
    # 转换后数据不足的行 dimensions 为空 dict，但带新 decision（含 low_quality）
    assert not is_old_format({
        "dimensions": {},
        "decision": {"recommendation": "insufficient_data", "low_quality": False},
    })


def test_is_old_format_true_when_old_style_decision():
    # 旧四维结果的 decision 也含 recommendation，但没有 low_quality —— 仍算旧格式
    assert is_old_format({
        "dimensions": {k: {"score": 60} for k in OLD_DIMS},
        "decision": {
            "recommendation": "ok",
            "status": "ok",
            "quadrant": "推荐",
            "grass_level": None,
            "growth_level": None,
        },
    })


# ---------- recompute_result ----------

def test_recompute_result_produces_new_five_dimensions():
    notes = _synthetic_notes(30)
    history = [
        {"fans": 45000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=35)).isoformat(), "source": "justoneapi"},
        {"fans": 50000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=5)).isoformat(), "source": "justoneapi"},
    ]
    task = _task(_old_result(notes, follower_history=history))
    new = recompute_result(task)

    assert set(new["dimensions"].keys()) == NEW_DIMS
    assert new["stage"] is not None
    assert "label" in new["stage"]
    assert new["overall"] is not None
    assert isinstance(new["overall"]["score"], (int, float))
    assert new["sampled"] is True
    assert new["coverage"]["total_notes"] == 30
    assert new["real_note_count"] == 30


def test_recompute_result_summarizes_follower_history():
    notes = _synthetic_notes(30)
    history = [
        {"fans": 45000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=35)).isoformat(), "source": "justoneapi"},
        {"fans": 50000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=5)).isoformat(), "source": "justoneapi"},
    ]
    task = _task(_old_result(notes, follower_history=history))
    new = recompute_result(task)

    fh = new["follower_history"]
    assert isinstance(fh, dict)
    assert fh["points"] == 2
    assert len(fh["series"]) == 2
    assert "growth_rate" in fh


def test_recompute_result_accepts_summarized_history_dict():
    """真实旧数据里 follower_history 可能是已汇总 dict（带 series），要能兼容。"""
    notes = _synthetic_notes(30)
    history = {
        "source": "justoneapi",
        "points": 2,
        "series": [
            {"fans": 45000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=35)).isoformat(), "source": "justoneapi"},
            {"fans": 50000, "snapshot_at": (datetime.now(CN_TZ) - timedelta(days=5)).isoformat(), "source": "justoneapi"},
        ],
    }
    task = _task(_old_result(notes, follower_history=history))
    new = recompute_result(task)
    assert new["follower_history"]["points"] == 2


def test_recompute_result_injects_nickname_from_old_result():
    notes = _synthetic_notes(30, nickname="作者A")
    task = _task(_old_result(notes, nickname="旧昵称"))
    assert recompute_result(task)["nickname"] == "旧昵称"


def test_recompute_result_nickname_fallback_to_note_author():
    notes = _synthetic_notes(30, nickname="作者A")
    task = _task(_old_result(notes, nickname=""))
    assert recompute_result(task)["nickname"] == "作者A"


def test_recompute_result_fallback_total_notes_from_task():
    notes = _synthetic_notes(30)
    result = _old_result(notes)
    result["coverage"] = {"sample_size": 30, "fetched_notes": 30}  # 无 total_notes
    task = _task(result, total_notes=40)
    new = recompute_result(task)
    assert new["coverage"]["total_notes"] == 40


def test_recompute_result_handles_empty_old_result():
    task = _task({})
    new = recompute_result(task)
    assert new["dimensions"] == {}
    assert new["overall"] is None
    assert new["stage"] is None
    assert new["confidence"] == "low"
    assert new["nickname"] == ""
