"""评论增强（可选）：意向词/水评/负面信号规则分析。"""
from __future__ import annotations

from app.services.scoring_config import load_scoring_config


def analyze_comments(comments: list[dict]) -> dict:
    """输入标准化评论列表（含 content），返回意向/水评/负面占比。"""
    cfg = load_scoring_config()["comments"]
    intent_kw = cfg["intent_keywords"]
    spam_kw = cfg["spam_keywords"]
    neg_kw = cfg["negative_keywords"]
    texts = [str(c.get("content") or "") for c in comments]
    texts = [t for t in texts if t]
    if not texts:
        return {"intent_ratio": 0.0, "spam_ratio": 0.0, "negative_ratio": 0.0, "sample": 0}
    # 三类信号可重叠：一条评论可能同时命中意向与水评，因此占比之和可 >1
    intent = sum(1 for t in texts if any(k in t for k in intent_kw))
    spam = sum(1 for t in texts if any(k in t for k in spam_kw))
    neg = sum(1 for t in texts if any(k in t for k in neg_kw))
    n = len(texts)
    return {
        "intent_ratio": round(intent / n, 4),
        "spam_ratio": round(spam / n, 4),
        "negative_ratio": round(neg / n, 4),
        "sample": n,
    }


async def collect_comments(crawler, notes: list[dict], note_limit: int | None = None, per_note: int | None = None) -> dict | None:
    """抓取代表性笔记（爆文 + 最新 + 随机）的评论并分析；失败降级返回 None。

    返回结构供 score_blogger 的 comment_analysis 使用：
    {"intent_ratio": float, "spam_ratio": float, "negative_ratio": float, "sample": int}
    """
    import asyncio
    import random

    cfg = load_scoring_config()["comments"]
    note_limit = note_limit or int(cfg["note_limit"])
    per_note = per_note or int(cfg["per_note"])
    if not notes:
        return None
    weighted = [(_weighted_for_comments(n), n) for n in notes]
    weighted.sort(key=lambda x: x[0], reverse=True)
    top_n = min(max(3, note_limit // 2), len(weighted))
    picked = [n for _, n in weighted[:top_n]]
    # 保证最新一篇进入样本（未在权重头部时补入，并用身份比较避免内容相同误判）
    newest = max(notes, key=lambda n: str(n.get("published_at") or ""), default=None)
    if newest is not None and all(n is not newest for n in picked):
        picked.insert(0, newest)
    rest = [n for _, n in weighted[top_n:]]
    if newest is not None:
        rest = [n for n in rest if n is not newest]
    if rest:
        picked.extend(random.sample(rest, max(0, min(note_limit - len(picked), len(rest)))))
    all_comments: list[dict] = []
    for n in picked[:note_limit]:
        note_id = n.get("platform_note_id") or n.get("id") or ""
        token = n.get("xsec_token", "")
        if not note_id:
            continue
        url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if token:
            url += f"?xsec_token={token}&xsec_source=pc_user"
        try:
            result = await asyncio.to_thread(crawler.get_comments, url)
        except Exception:
            continue
        if not result or not result.success:
            continue
        items = (result.data or []) if isinstance(result.data, list) else []
        all_comments.extend(items[:per_note])
        await asyncio.sleep(0.3)  # 风控节奏
    if not all_comments:
        return None
    return analyze_comments(all_comments)


def _weighted_for_comments(note: dict) -> int:
    st = note.get("stats") or {}
    return (int(st.get("liked", 0) or 0) + int(st.get("collected", 0) or 0) * 4
            + int(st.get("comments", 0) or 0) * 5 + int(st.get("shared", 0) or 0) * 6)
