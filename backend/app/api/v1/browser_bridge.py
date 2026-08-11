"""浏览器桥接口 — 接收自建扩展（AiRestro XHS Bridge）采集的数据。

对应方案阶段 3（自建扩展最小闭环）。内部桌面工具使用，仅监听本机，无鉴权。
数据经 processor.normalize_note 归一化后写入 note_details（幂等 upsert，不降级覆盖 full_stats 数据）。
"""

from __future__ import annotations
import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.note_detail import NoteDetail
from app.core.config import settings
from app.models.user import User
from app.models.knowledge_entry import KnowledgeEntry
from app.services.knowledge_base import sync_note
from app.services.knowledge_media import attach_entry_media

# PYTHONPATH=backend/services 时可用（start_services.py 已设置）
from crawler.processor import _parse_count, normalize_note

logger = logging.getLogger("crawler.bridge")
router = APIRouter(prefix="/bridge", tags=["bridge"])



async def _knowledge_user(db: AsyncSession):
    """本机免登录管理员账号，作为扩展采集数据在知识库中的归属。"""
    result = await db.execute(select(User).where(User.email == settings.LOCAL_ADMIN_EMAIL.lower()))
    return result.scalar_one_or_none()
class BridgeNoteRequest(BaseModel):
    note: dict = Field(..., description="XHS API 形状的笔记对象（含 note_card）")


class BridgeCommentsRequest(BaseModel):
    noteId: str = ""
    comments: list[dict] = Field(default_factory=list)


class BridgeBatchRequest(BaseModel):
    notes: list[dict] = Field(..., description="笔记对象列表")


async def _enrich_captured_note(note: dict) -> dict:
    """笔记为空壳时用后端爬虫按 id+token 补抓详情，避免扩展只抓到空数据。"""
    try:
        normalized = normalize_note(note)
        if note.get("capture_has_full_stats") is True:
            return note
        # 旧版扩展没有完整度标记：只有空壳才触发补抓，避免无谓请求
        if note.get("capture_has_full_stats") is None:
            if normalized.get("title") or normalized.get("cover_url") or normalized.get("image_urls"):
                return note
        note_id = normalized.get("platform_note_id") or ""
        token = normalized.get("xsec_token") or ""
        if not note_id or not token:
            return note
        from app.api.v1.notes import _extract_detail_items
        from crawler.config import get_cookie, get_proxy_pool, get_delay_settings
        from crawler.xhs import XhsCrawler

        min_d, max_d, retries = get_delay_settings()
        crawler = XhsCrawler(get_cookie(), proxy_pool=get_proxy_pool(), min_delay=min_d, max_delay=max_d, max_retries=retries)
        url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_user"
        detail = crawler.get_note_detail(url)
        items = _extract_detail_items(detail)
        if items:
            enriched = dict(items[0])
            enriched["id"] = note_id
            enriched["xsec_token"] = token
            return enriched
    except Exception:
        pass
    return note


async def _upsert_note(session: AsyncSession, note: dict) -> dict:
    """归一化并幂等 upsert；已有 full_stats 且新数据无完整互动时保留已有。"""
    normalized = normalize_note(note)
    author = normalized.get("author") or {}
    xhs_user_id = str(author.get("id") or "unknown")
    note_id = str(normalized.get("platform_note_id") or "")
    stats_source = str(note.get("stats_source") or (note.get("note_card") or {}).get("stats_source") or "")
    interact = (note.get("note_card") or {}).get("interact_info") or {}
    has_counts = any(_parse_count(interact.get(k) or 0) > 0 for k in ("liked_count", "collected_count", "comment_count", "shared_count", "share_count"))
    if note.get("capture_has_full_stats") is True:
        incoming_full = True
    elif note.get("capture_has_full_stats") is False:
        incoming_full = False
    else:
        incoming_full = stats_source in ("capture", "state", "feed") and has_counts
    if has_counts and not stats_source:
        stats_source = "capture"
    normalized["full_stats"] = incoming_full
    if stats_source:
        normalized["stats_source"] = stats_source

    existing = await session.execute(
        select(NoteDetail).where(
            NoteDetail.xhs_user_id == xhs_user_id,
            NoteDetail.platform_note_id == note_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        old = row.detail_json or {}
        if old.get("full_stats") and not incoming_full:
            return {"note_id": note_id, "updated": False, "kept_existing": True}
        row.detail_json = normalized
        row.fetched_at = datetime.now(timezone.utc)
        return {"note_id": note_id, "updated": True, "kept_existing": False}
    session.add(NoteDetail(xhs_user_id=xhs_user_id, platform_note_id=note_id, detail_json=normalized))
    return {"note_id": note_id, "inserted": True}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "browser-bridge"}


@router.post("/notes")
async def ingest_note(body: BridgeNoteRequest, db: AsyncSession = Depends(get_db)) -> dict:
    note = await _enrich_captured_note(body.note)
    result = await _upsert_note(db, note)
    kb_user = await _knowledge_user(db)
    result["knowledge_synced"] = False
    result["media_downloaded"] = {"images": 0, "video": False}
    if kb_user is not None:
        try:
            normalized = normalize_note(note)
            note_id = normalized.get("platform_note_id") or ""
            if await sync_note(db, kb_user.id, normalized, source="extension"):
                result["knowledge_synced"] = True
            if note_id:
                entry = (
                    await db.execute(
                        select(KnowledgeEntry).where(
                            KnowledgeEntry.user_id == kb_user.id,
                            KnowledgeEntry.platform_note_id == note_id,
                        )
                    )
                ).scalar_one_or_none()
                if entry:
                    result["media_downloaded"] = await attach_entry_media(db, entry, normalized)
        except Exception:
            result["knowledge_synced"] = False
    await db.commit()
    logger.info("bridge note %s knowledge_synced=%s media=%s", result.get("note_id"), result.get("knowledge_synced"), result.get("media_downloaded"))
    return {"success": True, **result}


@router.post("/batch")
async def ingest_batch(body: BridgeBatchRequest, db: AsyncSession = Depends(get_db)) -> dict:
    results = []
    for raw_note in body.notes:
        note = await _enrich_captured_note(raw_note)
        results.append(await _upsert_note(db, note))
    kb_user = await _knowledge_user(db)
    knowledge_synced = 0
    media_downloaded = 0
    if kb_user is not None:
        for raw_note in body.notes:
            note = await _enrich_captured_note(raw_note)
            try:
                normalized = normalize_note(note)
                note_id = normalized.get("platform_note_id") or ""
                if await sync_note(db, kb_user.id, normalized, source="extension"):
                    knowledge_synced += 1
                if note_id:
                    entry = (
                        await db.execute(
                            select(KnowledgeEntry).where(
                                KnowledgeEntry.user_id == kb_user.id,
                                KnowledgeEntry.platform_note_id == note_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if entry:
                        media = await attach_entry_media(db, entry, normalized)
                        if media.get("images") or media.get("video"):
                            media_downloaded += 1
            except Exception:
                continue
    await db.commit()
    inserted = sum(1 for r in results if r.get("inserted"))
    updated = sum(1 for r in results if r.get("updated"))
    skipped = sum(1 for r in results if r.get("kept_existing"))
    logger.info("bridge batch total=%s knowledge_synced=%s media_downloaded=%s kb_user=%s", len(results), knowledge_synced, media_downloaded, bool(kb_user))
    return {"success": True, "total": len(results), "inserted": inserted, "updated": updated, "skipped_kept_existing": skipped, "knowledge_synced": knowledge_synced, "media_downloaded": media_downloaded, "results": results}

@router.post("/comments")
async def ingest_comments(body: BridgeCommentsRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """把评论快照合并进对应笔记，并同步到知识库条目。"""
    if not body.noteId or not body.comments:
        return {"success": True, "stored": False, "reason": "noteId 或 comments 为空"}
    rows = await db.execute(select(NoteDetail).where(NoteDetail.platform_note_id == body.noteId))
    matched = rows.scalars().all()
    stored = 0
    for row in matched:
        d = dict(row.detail_json or {})
        d["comments"] = body.comments
        d["comments_captured_at"] = datetime.now(timezone.utc).isoformat()
        row.detail_json = d
        stored += 1

    kb_user = await _knowledge_user(db)
    knowledge_synced = 0
    if kb_user is not None:
        krows = await db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.user_id == kb_user.id,
                KnowledgeEntry.platform_note_id == body.noteId,
            )
        )
        entries = krows.scalars().all()
        if not entries:
            # 知识库还没有这条笔记时，用缓存详情补建条目再挂评论
            for row in matched:
                try:
                    await sync_note(db, kb_user.id, row.detail_json or {}, source="extension")
                except Exception:
                    continue
            krows = await db.execute(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.user_id == kb_user.id,
                    KnowledgeEntry.platform_note_id == body.noteId,
                )
            )
            entries = krows.scalars().all()
        for entry in entries:
            entry.comments = body.comments
            knowledge_synced += 1

    await db.commit()
    logger.info("bridge comments note=%s stored=%s knowledge_synced=%s", body.noteId, stored, knowledge_synced)
    return {"success": True, "stored": stored, "count": len(body.comments), "knowledge_synced": knowledge_synced}
