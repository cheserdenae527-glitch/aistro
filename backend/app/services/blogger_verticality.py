# backend/app/services/blogger_verticality.py
"""内容垂直度：餐饮/美食关键词分类（V1 规则版，Phase 2 可换大模型）。"""
from __future__ import annotations

from app.services.scoring_config import load_scoring_config


def _keywords() -> list[str]:
    return load_scoring_config()["verticality"]["food_keywords"]


def _note_text(note: dict) -> str:
    parts = [str(note.get("title") or ""), str(note.get("desc") or "")]
    tags = note.get("tags") or []
    parts.extend(str(t) for t in tags if isinstance(t, str))
    return " ".join(parts)


def is_food_note(note: dict, keywords: list[str] | None = None) -> bool:
    """标题/正文/标签任一命中美食关键词即判定为餐饮相关；无文本则 False。"""
    text = _note_text(note).strip()
    if not text:
        return False
    kws = keywords if keywords is not None else _keywords()
    return any(kw in text for kw in kws)


def food_verticality(notes: list[dict]) -> dict:
    """返回垂直度评分结果。复用 blogger_scoring._interpolate（升序锚点，与 C9 一致）。

    函数内 import 避免与 blogger_scoring 顶层相互导入（blogger_scoring 顶层
    会 import food_verticality，这里在调用时才取 _interpolate）。
    """
    from app.services.blogger_scoring import _interpolate

    cfg = load_scoring_config()["verticality"]
    kws = cfg["food_keywords"]
    points = cfg["points"]  # [(0.2,10),(0.4,40),(0.6,70),(0.8,100)] 升序
    food = 0
    judged_count = 0
    for n in notes:
        text = _note_text(n).strip()
        if not text:
            continue
        judged_count += 1
        if any(kw in text for kw in kws):
            food += 1
    ratio = food / judged_count if judged_count else 0.0
    score = round(_interpolate(points, ratio), 1)
    confidence = "high" if judged_count > 0 and judged_count >= len(notes) * 0.8 else "low"
    return {
        "score": score,
        "confidence": confidence,
        "detail": {"food_ratio": round(ratio, 4), "food_notes": food, "judged_notes": judged_count},
    }
