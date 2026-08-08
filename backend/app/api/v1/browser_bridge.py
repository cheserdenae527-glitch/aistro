"""浏览器桥接口 — 接收自建扩展（AiRestro XHS Bridge）采集的数据。

对应方案阶段 3（自建扩展最小闭环）。内部桌面工具使用，仅监听本机，无鉴权。
数据经 processor.normalize_note 归一化后写入 note_details（幂等 upsert，不降级覆盖 full_stats 数据）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.note_detail import NoteDetail

# PYTHONPATH=backend/services 时可用（start_services.py 已设置）
from crawler.processor import normalize_note

router = APIRouter(prefix="/bridge", tags=["bridge"])


class BridgeNoteRequest(BaseModel):
    note: dict = Field(..., description="XHS API 形状的笔记对象（含 note_card）")


class BridgeCommentsRequest(BaseModel):
    noteId: str = ""
    comments: list[dict] = Field(default_factory=list)


class BridgeBatchRequest(BaseModel):
    notes: list[dict] = Field(..., description="笔记对象列表")


async def _upsert_note(session: AsyncSession, note: dict) -> dict:
    """归一化并幂等 upsert；已有 full_stats 且新数据无完整互动时保留已有。"""
    normalized = normalize_note(note)
    author = normalized.get("author") or {}
    xhs_user_id = str(author.get("id") or "unknown")
    note_id = str(normalized.get("platform_note_id") or "")
    stats_source = str(note.get("stats_source") or (note.get("note_card") or {}).get("stats_source") or "")
    interact = (note.get("note_card") or {}).get("interact_info") or {}
    has_counts = any(int(interact.get(k) or 0) > 0 for k in ("liked_count", "collected_count", "comment_count", "shared_count"))
    incoming_full = stats_source in ("capture", "state", "feed") or has_counts or bool(note.get("capture_has_full_stats"))
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
    result = await _upsert_note(db, body.note)
    await db.commit()
    return {"success": True, **result}


@router.post("/batch")
async def ingest_batch(body: BridgeBatchRequest, db: AsyncSession = Depends(get_db)) -> dict:
    results = []
    for note in body.notes:
        results.append(await _upsert_note(db, note))
    await db.commit()
    inserted = sum(1 for r in results if r.get("inserted"))
    updated = sum(1 for r in results if r.get("updated"))
    skipped = sum(1 for r in results if r.get("kept_existing"))
    return {"success": True, "total": len(results), "inserted": inserted, "updated": updated, "skipped_kept_existing": skipped, "results": results}


@router.post("/comments")
async def ingest_comments(body: BridgeCommentsRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """把评论快照合并进对应笔记的 detail_json.comments（阶段 4 再独立落表）。"""
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
    if stored:
        await db.commit()
    return {"success": True, "stored": stored, "count": len(body.comments)}
