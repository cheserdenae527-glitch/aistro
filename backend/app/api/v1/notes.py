"""笔记浏览代理 API — 直接封装 XHS 搜索/详情/评论。"""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.user import User
from crawler.processor import normalize_note, normalize_comment
from crawler.xhs import XhsCrawler

router = APIRouter(prefix="/notes", tags=["notes"])


def _get_crawler():
    from crawler.config import get_cookie, get_proxy_pool, get_delay_settings
    cookie = get_cookie()
    proxies = get_proxy_pool()
    min_d, max_d, retries = get_delay_settings()
    return XhsCrawler(cookie, proxy_pool=proxies, min_delay=min_d, max_delay=max_d, max_retries=retries)


class SearchNotesRequest(BaseModel):
    query: str
    limit: int = 20
    sort: int = 0
    note_type: int = 0
    time_range: int = 0


@router.post("/search")
async def search_notes(
    body: SearchNotesRequest,
    user: User = Depends(get_current_user),
):
    """搜索小红书笔记，返回标准化结果。"""
    sort_map = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}
    sort_choice = sort_map.get(body.sort, 0)
    crawler = _get_crawler()
    result = crawler.search_notes(
        body.query, limit=body.limit,
        sort_type=sort_choice, note_type=body.note_type, time_range=body.time_range,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "搜索失败")
    return {"items": [normalize_note(n) for n in result.data], "stats": result.stats}


@router.get("/{note_id}")
async def get_note_detail(
    note_id: str,
    xsec_token: str = Query(""),
    user: User = Depends(get_current_user),
):
    """获取笔记详情（需 xsec_token）。"""
    if not xsec_token:
        raise HTTPException(status_code=400, detail="xsec_token is required")
    url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
    crawler = _get_crawler()
    result = crawler.get_note_detail(url)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "获取失败")
    items = result.data
    if not items:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return normalize_note(items[0])


@router.get("/{note_id}/comments")
async def get_note_comments(
    note_id: str,
    xsec_token: str = Query(""),
    user: User = Depends(get_current_user),
):
    """获取笔记评论（需 xsec_token）。"""
    if not xsec_token:
        raise HTTPException(status_code=400, detail="xsec_token is required")
    url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
    crawler = _get_crawler()
    result = crawler.get_comments(url)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "获取失败")
    return {"items": [normalize_comment(c, note_id) for c in result.data]}
