# backend/tests/test_blogger_verticality.py
from app.services.blogger_verticality import food_verticality, is_food_note


def _note(title="", desc="", tags=None):
    return {"title": title, "desc": desc, "tags": tags or []}


def test_is_food_note_by_title_desc_tags():
    assert is_food_note(_note(title="周末探店 这家火锅绝了"))
    assert is_food_note(_note(desc="美食打卡日记，人均 80"))
    assert is_food_note(_note(tags=["美食", "探店"]))
    assert not is_food_note(_note(title="OOTD 秋季穿搭分享"))
    assert not is_food_note(_note())  # 无法判定 → False（不计入分子）


def test_food_verticality_ratio_and_score():
    notes = [_note(title="探店打卡") for _ in range(10)] + [_note(title="穿搭分享") for _ in range(4)]
    res = food_verticality(notes)
    assert res["detail"]["judged_notes"] == 14
    assert res["detail"]["food_notes"] == 10
    # 实现按 4 位小数舍入（与 food_verticality 的 detail 契约一致）
    assert res["detail"]["food_ratio"] == round(10 / 14, 4)
    # 71.4% 位于升序锚点 (0.6→70) 与 (0.8→100) 之间，线性插值得分 87.1
    assert res["score"] == 87.1
    assert res["confidence"] == "high"


def test_food_verticality_all_non_food_floor():
    notes = [_note(title="穿搭分享"), _note(title="旅行日记"), _note(title="护肤日常")]
    res = food_verticality(notes)
    assert res["detail"]["judged_notes"] == 3
    assert res["detail"]["food_notes"] == 0
    assert res["detail"]["food_ratio"] == 0.0
    assert res["score"] == 10.0  # 低于最低锚点 0.2 → 取下限 10
    assert res["confidence"] == "high"


def test_food_verticality_empty_notes_low_confidence():
    res = food_verticality([])
    assert res["detail"]["judged_notes"] == 0
    assert res["detail"]["food_notes"] == 0
    assert res["detail"]["food_ratio"] == 0.0
    assert res["score"] == 10.0
    assert res["confidence"] == "low"  # 无可判定笔记 → 置信度降为低


def test_food_verticality_low_judged_notes_low_confidence():
    notes = [_note(title="探店打卡") for _ in range(6)] + [_note() for _ in range(10)]
    res = food_verticality(notes)
    assert res["detail"]["judged_notes"] == 6
    assert res["confidence"] == "low"
