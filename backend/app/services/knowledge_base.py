"""爬虫知识库服务 — 笔记素材沉淀、检索与统计。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_entry import KnowledgeEntry
from crawler.processor import _parse_count

logger = logging.getLogger("crawler.knowledge")

_SORT_MAP = {
    "hot": (KnowledgeEntry.liked_count + KnowledgeEntry.collected_count + KnowledgeEntry.comments_count + KnowledgeEntry.shared_count).desc(),
    "new": KnowledgeEntry.published_at.desc().nullslast(),
    "likes": KnowledgeEntry.liked_count.desc(),
    "collected": KnowledgeEntry.collected_count.desc(),
    "comments": KnowledgeEntry.comments_count.desc(),
    "shared": KnowledgeEntry.shared_count.desc(),
}


def _parse_dt(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _extract_author(note: dict) -> dict:
    a = note.get("author") or {}
    if isinstance(a, dict):
        return {
            "id": a.get("id") or a.get("user_id") or "",
            "nickname": a.get("nickname") or a.get("nick_name") or "",
            "avatar": a.get("avatar") or "",
        }
    return {"id": "", "nickname": "", "avatar": ""}


def _extract_stats(note: dict) -> dict:
    st = note.get("stats") or {}
    if not isinstance(st, dict):
        st = {}
    data = {
        "liked": _parse_count(st.get("liked")),
        "collected": _parse_count(st.get("collected")),
        "comments": _parse_count(st.get("comments")),
        "shared": _parse_count(st.get("shared")),
    }
    return data


def _extract_topics(tags: list) -> list[str]:
    """从话题标签提取分类 topic，去掉 # 与 [话题] 后缀，去重保序。"""
    topics: list[str] = []
    seen = set()
    for tag in tags or []:
        s = str(tag or "").strip().lstrip("#").strip()
        s = s.replace("[话题]", "").replace("…", "").strip()
        if not s or s == "小红书" or s in seen:
            continue
        seen.add(s)
        topics.append(s)
        if len(topics) >= 30:
            break
    return topics


def _build_content_md(data: dict, author: dict, stats: dict, topics: list[str]) -> str:
    tags = "、".join(str(t) for t in (data.get("tags") or [])[:20]) or "-"
    topic_text = "、".join(topics) or "-"
    lines = [
        f"# {data.get('title') or '无标题'}",
        "",
        f"- 作者：{author['nickname'] or '-'}",
        f"- 类型：{data.get('note_type') or 'normal'}",
        f"- 点赞 {stats['liked']} · 收藏 {stats['collected']} · 评论 {stats['comments']} · 分享 {stats['shared']}",
        f"- 原文：{data.get('note_url') or '-'}",
        "",
        (data.get("desc") or "").strip() or "（无正文）",
        "",
        f"标签：{tags}",
        f"话题：{topic_text}",
    ]
    return "\n".join(lines)


def note_to_entry_data(note: dict) -> dict:
    """把 normalize_note 产物/前端笔记卡片转成入库字段。"""
    author = _extract_author(note)
    stats = _extract_stats(note)
    platform_note_id = str(note.get("platform_note_id") or note.get("id") or note.get("note_id") or "")
    note_url = note.get("note_url") or ""
    if not note_url and platform_note_id:
        note_url = f"https://www.xiaohongshu.com/explore/{platform_note_id}"
    data = {
        "platform_note_id": platform_note_id,
        "xhs_user_id": str(author["id"] or note.get("xhs_user_id") or ""),
        "author_nickname": author["nickname"],
        "author_avatar": author["avatar"],
        "title": str(note.get("title") or note.get("display_title") or ""),
        "desc": note.get("desc") or "",
        "note_type": str(note.get("type") or "normal"),
        "cover_url": note.get("cover_url") or "",
        "image_urls": note.get("image_urls") or [],
        "video_url": note.get("video_url") or "",
        "tags": note.get("tags") or [],
        "stats": stats,
        "liked_count": stats["liked"],
        "collected_count": stats["collected"],
        "comments_count": stats["comments"],
        "shared_count": stats["shared"],
        "published_at": _parse_dt(note.get("published_at")),
        "note_url": note_url,
        "topics": _extract_topics(note.get("tags") or []),
        "content_md": None,
    }
    data["content_md"] = _build_content_md(data, author, stats, data.get("topics") or [])
    return data


async def sync_note(db: AsyncSession, user_id: uuid.UUID, note: dict, source: str = "manual") -> bool:
    """把一篇笔记写入知识库（按 user_id + platform_note_id 去重）。"""
    data = note_to_entry_data(note)
    platform_note_id = data["platform_note_id"]
    if not platform_note_id:
        return False
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.user_id == user_id,
            KnowledgeEntry.platform_note_id == platform_note_id,
        )
    )
    row = result.scalar_one_or_none()
    data["source"] = source
    if row:
        for k, v in data.items():
            if k == "platform_note_id":
                continue
            setattr(row, k, v)
        row.synced_at = datetime.now().astimezone()
    else:
        db.add(KnowledgeEntry(user_id=user_id, **data))
    return True
async def sync_notes(db: AsyncSession, user_id: uuid.UUID, notes: list[dict], source: str = "manual") -> int:
    """批量写入知识库，返回成功条数。"""
    count = 0
    for note in notes or []:
        if isinstance(note, dict) and await sync_note(db, user_id, note, source=source):
            count += 1
    return count


def entry_to_payload(entry: KnowledgeEntry) -> dict:
    return {
        "id": str(entry.id),
        "platform": entry.platform,
        "platform_note_id": entry.platform_note_id,
        "xhs_user_id": entry.xhs_user_id,
        "author_nickname": entry.author_nickname,
        "author_avatar": entry.author_avatar,
        "title": entry.title,
        "desc": entry.desc,
        "note_type": entry.note_type,
        "cover_url": entry.cover_url,
        "image_urls": entry.image_urls or [],
        "video_url": entry.video_url,
        "tags": entry.tags or [],
        "comments": entry.comments or [],
        "topics": entry.topics or [],
        "content_md": entry.content_md,
        "cover_local": entry.cover_local,
        "image_urls_local": entry.image_urls_local or [],
        "video_local": entry.video_local,
        "stats": entry.stats or {},
        "liked_count": entry.liked_count,
        "collected_count": entry.collected_count,
        "comments_count": entry.comments_count,
        "shared_count": entry.shared_count,
        "published_at": entry.published_at.isoformat() if entry.published_at else None,
        "source": entry.source,
        "note_url": entry.note_url,
        "synced_at": entry.synced_at.isoformat() if entry.synced_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


async def list_entries(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    keyword: str = "",
    author: str = "",
    note_type: str = "",
    source: str = "",
    topic: str = "",
    min_likes: int = 0,
    sort: str = "hot",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conds = [KnowledgeEntry.user_id == user_id]
    if keyword:
        like = f"%{keyword.strip()}%"
        conds.append(
            or_(
                KnowledgeEntry.title.ilike(like),
                KnowledgeEntry.desc.ilike(like),
                KnowledgeEntry.author_nickname.ilike(like),
            )
        )
    if author:
        conds.append(KnowledgeEntry.author_nickname.ilike(f"%{author.strip()}%"))
    if note_type:
        conds.append(KnowledgeEntry.note_type == note_type)
    if source:
        conds.append(KnowledgeEntry.source == source)
    if topic:
        conds.append(KnowledgeEntry.topics.contains([topic.strip()]))
    if min_likes > 0:
        conds.append(KnowledgeEntry.liked_count >= min_likes)
    total = (await db.execute(select(func.count()).select_from(KnowledgeEntry).where(*conds))).scalar() or 0
    order = _SORT_MAP.get(sort, _SORT_MAP["hot"])
    rows = (
        await db.execute(
            select(KnowledgeEntry)
            .where(*conds)
            .order_by(order, KnowledgeEntry.synced_at.desc())
            .offset((max(1, page) - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {"items": [entry_to_payload(e) for e in rows], "total": total, "page": page, "page_size": page_size}


async def get_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> KnowledgeEntry | None:
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id, KnowledgeEntry.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id, KnowledgeEntry.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    return True


async def get_stats(db: AsyncSession, user_id: uuid.UUID) -> dict:
    rows = (await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.user_id == user_id))).scalars().all()
    total = len(rows)
    images = sum(1 for r in rows if r.note_type != "video")
    videos = sum(1 for r in rows if r.note_type == "video")
    topic_counter: dict[str, int] = {}
    platform_counter: dict[str, int] = {}
    for r in rows:
        platform_counter[r.platform] = platform_counter.get(r.platform, 0) + 1
        for t in (r.topics or []):
            topic_counter[t] = topic_counter.get(t, 0) + 1
    top_topics = dict(sorted(topic_counter.items(), key=lambda x: -x[1])[:20])
    return {
        "total": total,
        "images": images,
        "videos": videos,
        "total_likes": sum(r.liked_count for r in rows),
        "total_comments": sum(r.comments_count for r in rows),
        "total_collected": sum(r.collected_count for r in rows),
        "total_shared": sum(r.shared_count for r in rows),
        "topics": top_topics,
        "platforms": platform_counter,
        "sources": {
            s: sum(1 for r in rows if r.source == s) for s in sorted({r.source for r in rows})
        },
    }
