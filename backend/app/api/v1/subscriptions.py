"""订阅博主 API。"""
from __future__ import annotations
import asyncio
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subscription import Subscription, SubscriptionSnapshot
from app.models.user import User
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SnapshotResponse
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# 模块级缓存运行时路径
_XHS_RT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "services", "crawler", "xhs", "scripts", "runtime", "spider_xhs_core"))


_xhs_api = None
_xhs_auth = None
_xhs_api_lock = threading.Lock()

def _get_xhs_api():
    global _xhs_api, _xhs_auth
    with _xhs_api_lock:
        if _xhs_api is not None:
            return _xhs_api
        if _XHS_RT not in sys.path:
            sys.path.insert(0, _XHS_RT)
        old = os.getcwd()
        os.chdir(_XHS_RT)
        node = shutil.which('node')
        node_dir = os.path.dirname(node) if node else None
        if not node_dir:
            raise RuntimeError('Node.js 未安装，无法初始化小红书 API')
        if node_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = node_dir + os.pathsep + os.environ.get('PATH', '')
        try:
            from crawler.config import get_cookie
            from xhs_utils.xhs_pc import XHSPcAuth
            from apis.xhs_pc_apis import XHS_Apis
            _xhs_auth = XHSPcAuth.from_cookie(get_cookie())
            _xhs_api = XHS_Apis(_xhs_auth)
            return _xhs_api
        finally:
            os.chdir(old)


@router.get("")
async def list_subs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id).order_by(desc(Subscription.created_at)))
    return [SubscriptionResponse.model_validate(s) for s in result.scalars().all()]

@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_sub(body: SubscriptionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Subscription).where(Subscription.user_id == user.id, Subscription.xhs_user_id == body.xhs_user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="已订阅")
    sub = Subscription(user_id=user.id, **body.model_dump())
    db.add(sub); await db.flush()
    return SubscriptionResponse.model_validate(sub)

@router.post("/{sub_id}/refresh", response_model=SubscriptionResponse)
async def refresh_sub(sub_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    if not sub: raise HTTPException(status_code=404, detail="Not found")
    api = await asyncio.to_thread(_get_xhs_api)
    # 用户资料
    success, msg, raw = await asyncio.to_thread(api.get_user_info, sub.xhs_user_id)
    if success and raw:
        d = raw.get('data', raw)
        bi = d.get('basic_info', {})
        sub.nickname = bi.get('nickname', sub.nickname)
        sub.avatar = bi.get('imageb', '') or bi.get('images', '')
        if isinstance(sub.avatar, list) and sub.avatar:
            sub.avatar = sub.avatar[0]
        for item in d.get('interactions', []):
            if isinstance(item, dict):
                t = item.get('type',''); c = int(item.get('count', 0))
                if t == 'fans': sub.follower_count = c
                elif t == 'follows': sub.following_count = c
    # 笔记数
    success2, msg2, notes_data = await asyncio.to_thread(
        api.get_user_all_notes,
        f'https://www.xiaohongshu.com/user/profile/{sub.xhs_user_id}',
    )
    if success2 and notes_data:
        sub.note_count = len(notes_data)
        from crawler.processor import normalize_note
        _notes = []
        for n in (notes_data or []):
            n.setdefault("id", n.get("note_id", ""))
            _notes.append(normalize_note(n))
    else:
        _notes = []
    sub.last_crawled_at = datetime.now(timezone.utc)
    snap = SubscriptionSnapshot(subscription_id=sub.id, note_count=sub.note_count, follower_count=sub.follower_count, following_count=sub.following_count)
    db.add(snap); await db.flush()
    payload = SubscriptionResponse.model_validate(sub).model_dump()
    payload["notes"] = _notes[:50]
    return payload

@router.delete("/{sub_id}", status_code=204)
async def delete_sub(sub_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    if not sub: raise HTTPException(status_code=404, detail="Not found")
    await db.delete(sub)

@router.get("/{sub_id}/notes")
async def get_sub_notes(sub_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    if not sub: raise HTTPException(status_code=404, detail="Not found")
    from crawler.processor import normalize_note
    api = await asyncio.to_thread(_get_xhs_api)
    success, msg, raw_notes = await asyncio.to_thread(
        api.get_user_all_notes,
        f'https://www.xiaohongshu.com/user/profile/{sub.xhs_user_id}',
    )
    if not success: raise HTTPException(status_code=502, detail=str(msg))
    if not raw_notes: return {'notes': [], 'nickname': sub.nickname}
    for n in raw_notes: n.setdefault("id", n.get("note_id", ""))
    notes = [normalize_note(n) for n in raw_notes[:50]]
    return {"notes": notes, "nickname": sub.nickname}

@router.get("/{sub_id}/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(sub_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sub = await db.execute(select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id))
    if sub.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(select(SubscriptionSnapshot).where(SubscriptionSnapshot.subscription_id == sub_id).order_by(desc(SubscriptionSnapshot.crawled_at)).limit(30))
    return [SnapshotResponse.model_validate(s) for s in result.scalars().all()]

