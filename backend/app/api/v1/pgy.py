"""蒲公英（JustOneAPI）官方补充数据接口 — 创作者资料 / 粉丝摘要 / 相似创作者。

供博主分析界面展示官方报价、粉丝画像与相似达人；失败时返回 {ok: false, error}，
前端降级为空态，不阻塞本地爬虫评分。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.models.user import User
from app.services.justoneapi_client import (
    fetch_creator_profile,
    fetch_fans_summary,
    fetch_similar_kol,
)

router = APIRouter(prefix="/pgy", tags=["pgy"])


@router.get("/users/{user_id}/creator-profile")
async def creator_profile(
    user_id: str,
    user: User = Depends(get_current_user),
):
    return await asyncio.to_thread(fetch_creator_profile, user_id)


@router.get("/users/{user_id}/fans-summary")
async def fans_summary(
    user_id: str,
    user: User = Depends(get_current_user),
):
    return await asyncio.to_thread(fetch_fans_summary, user_id)


@router.get("/users/{user_id}/similar")
async def similar_kol(
    user_id: str,
    page_num: int = Query(1, ge=1, le=20),
    user: User = Depends(get_current_user),
):
    return await asyncio.to_thread(fetch_similar_kol, user_id, page_num)
