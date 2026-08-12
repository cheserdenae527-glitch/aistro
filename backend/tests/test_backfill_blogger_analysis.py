"""Task C1：旧版博主分析结果回填脚本 — 纯函数单测（不连数据库）。

只测 scripts/backfill_blogger_analysis.py 里的纯函数/循环助手：
- is_old_format / _is_new_format：新旧格式判定（含 format_version 标记）
- recompute_result：旧 result 重算为新的五维 result
- _process_one / _apply_to_tasks：逐任务异常隔离、非 dict 守卫、dry-run
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

from backfill_blogger_analysis import (  # noqa: E402
    FORMAT_VERSION,
    _apply_to_tasks,
    _is_new_format,
    _process_one,
    is_old_format,
    recompute_result,
)

CN_TZ = timezone(timedelta(hours=8))
NEW_DIMS = {"seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend", "cost_effectiveness"}
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
    # 对齐 BloggerAnalysisTask 列：fetched_notes/coverage/confidence 恒存在
    return SimpleNamespace(
        id=uuid.uuid4(),
        xhs_user_id="xhs_test_001",
        follower_count=follower_count,
        total_notes=total_notes,
        fetched_notes=30,
        coverage=None,
        confidence=None,
        status="success",
        result=result,
    )


def _bad_notes() -> list[dict]:
    """能通过真实样本闸门、但会让 score_blogger 抛异常的 notes。"""
    notes = _synthetic_notes(30)
    notes[5]["stats"] = {"liked": "abc", "collected": 100, "comments": 10, "shared": 5}
    return notes


# ---------- is_old_format / _is_new_format ----------

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


def test_is_old_format_false_when_format_version_marker():
    assert not is_old_format({"format_version": FORMAT_VERSION})
    assert not is_old_format({"dimensions": {}, "format_version": FORMAT_VERSION})


def test_is_new_format_true_via_format_version():
    assert _is_new_format({"format_version": FORMAT_VERSION})
    assert _is_new_format({"dimensions": {"seeding_depth": {}}})
    assert _is_new_format({
        "dimensions": {},
        "decision": {"recommendation": "insufficient_data", "low_quality": False},
    })
    assert not _is_new_format({})
    assert not _is_new_format({"dimensions": {"trend": {}}})


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
    assert new["format_version"] == FORMAT_VERSION
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
    assert new["format_version"] == FORMAT_VERSION


# ---------- _process_one / _apply_to_tasks ----------

def test_process_one_isolates_recompute_error():
    bad = _task(_old_result(_bad_notes()))
    assert _process_one(bad, dry_run=False) == "error"
    # 失败行保持原样（旧格式），可被后续 --apply 重试
    assert is_old_format(bad.result)


def test_apply_to_tasks_continues_after_error():
    bad = _task(_old_result(_bad_notes()))
    good = _task(_old_result(_synthetic_notes(30)))
    old_count, skipped, updated = _apply_to_tasks([bad, good], dry_run=False)
    assert old_count == 2  # bad(error) + good(updated)
    assert skipped == 0
    assert updated == [good]
    assert good.result["format_version"] == FORMAT_VERSION


def test_process_one_skips_non_dict_result():
    for bad_result in (None, [], "oops"):
        task = SimpleNamespace(
            id=uuid.uuid4(),
            xhs_user_id="xhs_test_001",
            follower_count=0,
            total_notes=0,
            status="success",
            result=bad_result,
        )
        assert _process_one(task, dry_run=False) == "skipped_bad"
        # 不伪造结果：task.result 原样保留
        assert task.result is bad_result


def test_apply_to_tasks_counts_skipped_bad_and_new():
    non_dict = SimpleNamespace(
        id=uuid.uuid4(),
        xhs_user_id="xhs_test_001",
        follower_count=0,
        total_notes=0,
        status="success",
        result=None,
    )
    already_new = SimpleNamespace(
        id=uuid.uuid4(),
        xhs_user_id="xhs_test_001",
        follower_count=0,
        total_notes=0,
        status="success",
        result={"format_version": FORMAT_VERSION},
    )
    good = _task(_old_result(_synthetic_notes(30)))
    old_count, skipped, updated = _apply_to_tasks([non_dict, already_new, good], dry_run=True)
    assert old_count == 1
    assert skipped == 2
    assert updated == []


def test_process_one_dry_run_does_not_mutate():
    task = _task(_old_result(_synthetic_notes(30)))
    original = task.result
    assert _process_one(task, dry_run=True) == "dry_run"
    assert task.result is original
    assert task.confidence is None
    assert "format_version" not in task.result
