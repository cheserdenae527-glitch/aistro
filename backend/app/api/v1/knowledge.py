"""爬虫知识库 API — 素材沉淀、检索、统计与删除。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from app.models.knowledge_entry import KnowledgeEntry
from app.services.knowledge_media import backfill_entry_media
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.knowledge_base import (
    delete_entry,
    entry_to_payload,
    get_entry,
    get_stats,
    list_entries,
    sync_notes,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeNotesRequest(BaseModel):
    notes: list[dict] = Field(default_factory=list)
    source: str = "manual"


@router.get("")
async def list_knowledge(
    keyword: str = Query(""),
    author: str = Query(""),
    note_type: str = Query(""),
    source: str = Query(""),
    topic: str = Query(""),
    min_likes: int = Query(0, ge=0),
    sort: str = Query("hot"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_entries(
        db,
        user.id,
        keyword=keyword,
        author=author,
        note_type=note_type,
        source=source,
        topic=topic,
        min_likes=min_likes,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/stats")
async def knowledge_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_stats(db, user.id)


@router.post("/notes", status_code=201)
async def add_knowledge_notes(
    body: KnowledgeNotesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await sync_notes(db, user.id, body.notes, source=body.source)
    return {"synced": count, "source": body.source}


@router.post("/media/sync")
async def sync_all_media(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把缺少本地媒体的知识条目批量补下载封面/图片/视频。"""
    rows = (
        await db.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.user_id == user.id,
                or_(
                    KnowledgeEntry.cover_local.is_(None),
                    KnowledgeEntry.image_urls_local.is_(None),
                ),
            )
        )
    ).scalars().all()
    updated = 0
    failed = 0
    for entry in rows:
        try:
            res = await backfill_entry_media(db, entry)
            if res.get("images") or res.get("video"):
                updated += 1
        except Exception:
            failed += 1
    await db.commit()
    return {"scanned": len(rows), "updated": updated, "failed": failed}


@router.post("/{entry_id}/media")
async def sync_entry_media(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    entry = await get_entry(db, user.id, eid)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    result = await backfill_entry_media(db, entry)
    await db.commit()
    return result


@router.get("/{entry_id}")
async def get_knowledge_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    entry = await get_entry(db, user.id, eid)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    return entry_to_payload(entry)


@router.delete("/{entry_id}")
async def remove_knowledge_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        eid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    ok = await delete_entry(db, user.id, eid)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}



