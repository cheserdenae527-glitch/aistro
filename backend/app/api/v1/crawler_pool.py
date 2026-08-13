"""爬虫 Cookie 池 / IP 代理池管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.models.user import User

from crawler import config as crawler_config
from crawler import cookie_pool

router = APIRouter(prefix="/crawler/pool", tags=["crawl-pool"])


class CookieCreateRequest(BaseModel):
    cookie: str = Field(..., min_length=10)
    label: str = ""


class CookieUpdateRequest(BaseModel):
    cookie: str | None = None
    label: str | None = None
    status: str | None = None


@router.get("/cookies")
async def list_cookies(
    current_user: User = Depends(get_current_user),
):
    items = cookie_pool.list_cookies()
    return {"items": items, "stats": cookie_pool.pool_stats()}


@router.post("/cookies")
async def add_cookie(
    body: CookieCreateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        entry = cookie_pool.add_cookie(body.cookie, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return entry


@router.patch("/cookies/{cookie_id}")
async def update_cookie(
    cookie_id: str,
    body: CookieUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        entry = cookie_pool.update_cookie(
            cookie_id,
            label=body.label,
            cookie=body.cookie,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return entry


@router.delete("/cookies/{cookie_id}")
async def delete_cookie(
    cookie_id: str,
    current_user: User = Depends(get_current_user),
):
    if not cookie_pool.delete_cookie(cookie_id):
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return {"success": True}


@router.post("/cookies/{cookie_id}/unbind")
async def unbind_cookie(
    cookie_id: str,
    current_user: User = Depends(get_current_user),
):
    entry = cookie_pool.unbind_cookie(cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return entry


@router.post("/cookies/{cookie_id}/rebind")
async def rebind_cookie(
    cookie_id: str,
    current_user: User = Depends(get_current_user),
):
    entry = cookie_pool.rebind_cookie(cookie_id, crawler_config.get_proxy_pool())
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return entry


@router.get("/calls")
async def recent_calls(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    limit = max(1, min(limit, 200))
    return {"items": crawler_config.recent_request_logs(limit)}


@router.post("/cookies/check")
async def check_cookies(
    user: User = Depends(get_current_user),
):
    """主动探测池内可用 Cookie 登录态（check_cookie 真实验证），返回可用性摘要。"""
    from app.services.cookie_health_scheduler import CookieHealthScheduler

    await CookieHealthScheduler()._check_job()
    cookies = cookie_pool.list_cookies()
    return {
        "total": len(cookies),
        "available": sum(1 for c in cookies if c.get("status") == "available" and c.get("cookie")),
        "cooling": sum(1 for c in cookies if c.get("status") == "cooling"),
        "invalid": sum(1 for c in cookies if c.get("status") == "invalid"),
        "has_usable": any(c.get("status") == "available" and c.get("cookie") for c in cookies),
    }


@router.get("/proxies")
async def proxy_status(
    current_user: User = Depends(get_current_user),
):
    return crawler_config.proxy_pool_stats()


@router.post("/proxies/refresh")
async def refresh_proxies(
    current_user: User = Depends(get_current_user),
):
    try:
        crawler_config.refresh_short_proxies()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"代理刷新失败: {exc}")
    return crawler_config.proxy_pool_stats()
