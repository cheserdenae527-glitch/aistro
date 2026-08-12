"""笔记浏览代理 API — 直接封装 XHS 搜索/详情/评论。"""
from __future__ import annotations

import asyncio
import logging
import math
import statistics
import time
import uuid

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.analysis_task import BloggerAnalysisTask
from app.models.user import User
from crawler.processor import normalize_note, normalize_comment
from crawler.xhs import XhsCrawler

router = APIRouter(prefix="/notes", tags=["notes"])

logger = logging.getLogger("crawler.analysis_task_batch")


def _get_crawler(
    min_delay: float | None = None,
    max_delay: float | None = None,
    max_retries: int | None = None,
):
    from crawler.config import acquire_cookie, get_delay_settings
    cookie, cookie_id, sticky_pool = acquire_cookie()
    cfg_min, cfg_max, cfg_retries = get_delay_settings()
    return XhsCrawler(
        cookie,
        proxy_pool=sticky_pool,
        min_delay=min_delay if min_delay is not None else cfg_min,
        max_delay=max_delay if max_delay is not None else cfg_max,
        max_retries=max_retries if max_retries is not None else cfg_retries,
        cookie_id=cookie_id,
    )


class SearchUsersRequest(BaseModel):
    query: str
    limit: int = Field(20, ge=1, le=50)


def _parse_count(v) -> int:
    """把 '1.1万' / '123' 这类字符串转成数字。"""
    if isinstance(v, (int, float)):
        return int(v)
    if not v:
        return 0
    s = str(v).strip().replace(",", "")
    if "万" in s:
        try:
            return int(float(s.replace("万", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _normalize_user_summary(u: dict) -> dict:
    """把 Spider_XHS 搜索用户结果转成前端友好的结构。"""
    return {
        "user_id": u.get("user_id", u.get("id", "")),
        "nickname": u.get("nickname", u.get("nick_name", u.get("name", ""))),
        "avatar": u.get("avatar", u.get("images", u.get("image", ""))),
        "fans": _parse_count(u.get("fans", u.get("fans_total", u.get("follower_count", 0)))),
        "notes": _parse_count(u.get("notes", u.get("note_count", 0))),
        "desc": u.get("desc", u.get("signature", u.get("sub_title", ""))),
    }


@router.post("/search-users")
async def search_users(
    body: SearchUsersRequest,
    user: User = Depends(get_current_user),
):
    """搜索小红书博主/用户。"""
    crawler = _get_crawler()
    cache_key = f"search-users:{body.query}:{body.limit}"
    cached = _search_cache_get(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(crawler.search_users, body.query, body.limit)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "搜索失败")
    users = [_normalize_user_summary(u) for u in (result.data or [])]
    payload = {"items": users}
    _search_cache_set(cache_key, payload)
    return payload


class UserAnalysisRequest(BaseModel):
    nickname: str = ""
    fans: int = Field(0, ge=0)
    detail_limit: int = Field(10, ge=0, le=50)
    refresh: bool = Field(False, description="true 时跳过缓存强制重新抓取")


def _extract_detail_items(result) -> list[dict]:
    """从爬虫返回的详情响应中提取笔记对象列表。"""
    if not result.success:
        return []
    raw = result.data
    if isinstance(raw, dict):
        payload = raw.get("data")
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return [it for it in payload["items"] if isinstance(it, dict)]
        if raw.get("note_card"):
            return [raw]
    if isinstance(raw, list):
        return [it for it in raw if isinstance(it, dict)]
    return []


def _merge_detail_note(base: dict, detail_raw: dict) -> None:
    """用详情数据补齐列表笔记的发布时间与完整互动数据（空值不覆盖真实数据）。"""
    detail = normalize_note(detail_raw)
    for key in ("title", "desc", "type", "cover_url", "image_urls", "video_url", "tags"):
        if detail.get(key):
            base[key] = detail[key]
    if detail.get("published_at") is not None:
        base["published_at"] = detail["published_at"]
    detail_stats = detail.get("stats") or {}
    base_stats = base.setdefault("stats", {})
    for key in ("liked", "collected", "comments", "shared"):
        value = detail_stats.get(key)
        if value:
            base_stats[key] = value
        else:
            base_stats[key] = base_stats.get(key, 0)
    base["full_stats"] = bool(any(base_stats.get(key) for key in ("liked", "collected", "comments", "shared")))


# 搜索/作品短缓存：短时间重复搜索相同账号/关键词时直接命中，减少爬取与风控压力
_SEARCH_CACHE: dict[str, tuple[float, Any]] = {}
_SEARCH_CACHE_TTL = 300


def _search_cache_get(key: str):
    item = _SEARCH_CACHE.get(key)
    if item and time.time() - item[0] < _SEARCH_CACHE_TTL:
        return item[1]
    return None


def _search_cache_set(key: str, value: Any) -> None:
    _SEARCH_CACHE[key] = (time.time(), value)


def _note_likes(note: dict) -> int:
    st = note.get("stats") or {}
    return int(st.get("liked", 0) or 0)


def _weighted(st: dict) -> int:
    return int(st.get("liked", 0) or 0) + int(st.get("collected", 0) or 0) + int(st.get("comments", 0) or 0) * 4 + int(st.get("shared", 0) or 0) * 4


def _build_stratified_sample(notes: list[dict], detail_limit: int) -> list[int]:
    """按发布顺序分桶 + 桶内按点赞排序抽样，保底覆盖中位数区间。"""
    total = len(notes)
    if total <= detail_limit:
        return list(range(total))
    bucket_count = max(1, min(detail_limit // 2, 12))
    sample_indices: set[int] = set()
    bucket_size = max(1, math.ceil(total / bucket_count))
    for b in range(bucket_count):
        chunk_start = b * bucket_size
        chunk = notes[chunk_start:chunk_start + bucket_size]
        if not chunk:
            continue
        ranked = sorted(
            range(len(chunk)),
            key=lambda i: -_note_likes(chunk[i]),
        )
        take = 2 if len(sample_indices) + 2 <= detail_limit else 1
        for i in ranked[:take]:
            sample_indices.add(chunk_start + i)

    likes_sorted = sorted(_note_likes(n) for n in notes)
    median_likes = likes_sorted[len(likes_sorted) // 2]
    median_idx = min(range(total), key=lambda i: abs(_note_likes(notes[i]) - median_likes))
    if median_idx not in sample_indices and len(sample_indices) < detail_limit:
        sample_indices.add(median_idx)

    remaining = detail_limit - len(sample_indices)
    if remaining > 0:
        for i in sorted(range(total), key=lambda i: -_note_likes(notes[i])):
            if i in sample_indices:
                continue
            sample_indices.add(i)
            remaining -= 1
            if remaining <= 0:
                break
    return sorted(sample_indices)


async def _fetch_details_with_early_stop(crawler, notes: list[dict], indices: list[int], concurrency: int = 3) -> None:
    """分窗口并发抓详情，窗口间按均值稳定性 <3% 提前结束。"""
    means: list[float] = []
    stable_streak = 0
    if not indices:
        return
    pool_size = min(concurrency, len(indices))
    pool = [crawler] if pool_size <= 1 else [_get_crawler(min_delay=1.0, max_delay=2.0, max_retries=1) for _ in range(pool_size)]
    sem = asyncio.Semaphore(pool_size)

    async def one(idx: int) -> None:
        base_note = notes[idx]
        nid = base_note.get("platform_note_id") or base_note.get("id")
        token = base_note.get("xsec_token")
        if not nid or not token:
            return
        url = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_user"
        worker = pool[idx % len(pool)]
        async with sem:
            detail_result = await asyncio.to_thread(worker.get_note_detail, url)
        detail_items = _extract_detail_items(detail_result)
        if detail_items:
            _merge_detail_note(base_note, detail_items[0])

    for start in range(0, len(indices), pool_size):
        chunk = indices[start:start + pool_size]
        await asyncio.gather(*(one(idx) for idx in chunk))
        detailed = [n for n in notes if n.get("full_stats")]
        if len(detailed) >= 3:
            mean = statistics.fmean(_weighted(n["stats"]) for n in detailed)
            prev = means[-1] if means else None
            means.append(mean)
            if prev is not None and abs(mean - prev) / max(abs(prev), 1) < 0.03:
                stable_streak += 1
            else:
                stable_streak = 0
            if stable_streak >= 3:
                break


async def _enrich_note_details(notes: list[dict], indices: list[int], concurrency: int = 3) -> None:
    """并发抓详情补齐列表笔记的完整互动 / 时间 / 图片。"""
    if not indices:
        return
    pool_size = min(concurrency, len(indices))
    pool = [_get_crawler(min_delay=1.0, max_delay=2.0, max_retries=1) for _ in range(pool_size)]
    sem = asyncio.Semaphore(pool_size)

    async def one(idx: int) -> None:
        note = notes[idx]
        nid = note.get("platform_note_id") or note.get("id")
        token = note.get("xsec_token")
        if not nid or not token:
            return
        url = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_user"
        worker = pool[idx % len(pool)]
        async with sem:
            detail_result = await asyncio.to_thread(worker.get_note_detail, url)
        detail_items = _extract_detail_items(detail_result)
        if detail_items:
            _merge_detail_note(note, detail_items[0])

    await asyncio.gather(*(one(i) for i in indices))


def _estimate_unfetched_stats(notes: list[dict]) -> None:
    """用已抓详情样本拟合 (评论/收藏/分享)/点赞 比例，估算未抓笔记互动。"""
    detailed = [n for n in notes if n.get("full_stats")]
    if not detailed:
        return
    total_likes = sum(n["stats"]["liked"] for n in detailed)
    if total_likes <= 0:
        return
    ratios = {
        "comments": sum(n["stats"]["comments"] for n in detailed) / total_likes,
        "collected": sum(n["stats"]["collected"] for n in detailed) / total_likes,
        "shared": sum(n["stats"]["shared"] for n in detailed) / total_likes,
    }
    for note in notes:
        if note.get("full_stats"):
            continue
        likes = note["stats"]["liked"]
        note["stats"] = {
            "liked": likes,
            "collected": round(likes * ratios["collected"]),
            "comments": round(likes * ratios["comments"]),
            "shared": round(likes * ratios["shared"]),
        }
        note["estimated"] = True


@router.get("/users/{user_id}/notes")
async def get_user_notes_by_id(
    user_id: str,
    limit: int = Query(50, ge=1, le=100),
    nickname: str = Query(""),
    enrich_limit: int = Query(50, ge=0, le=100),
    user: User = Depends(get_current_user),
):
    """按博主 ID 抓取该账号的作品，避免同名账号串号；失败可回退昵称搜索。"""
    crawler = _get_crawler(min_delay=1.0, max_delay=2.0, max_retries=1)
    cache_key = f"user-notes:{user_id}:{limit}:{enrich_limit}"
    cached = _search_cache_get(cache_key)
    if cached is not None:
        return cached
    user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    fetch_cap = max(limit * 2, 100)
    notes_result = None
    for attempt in range(2):
        notes_result = await asyncio.to_thread(crawler.get_user_notes, user_url, max_notes=fetch_cap)
        if notes_result.success:
            break
        if attempt == 0:
            await asyncio.sleep(1.0)

    source = "user_notes"
    if not notes_result or not notes_result.success:
        # 作品接口被风控时，有昵称则回退搜索；否则返回明确错误
        if nickname:
            search_result = await asyncio.to_thread(crawler.search_notes, nickname, limit=limit)
            if search_result.success and search_result.data:
                raw_notes = search_result.data
                source = "search_fallback"
            else:
                raise HTTPException(
                    status_code=502,
                    detail="小红书风控限流，获取作品失败，请稍后重试或更新 Cookie",
                )
        else:
            detail = (notes_result.error if notes_result else "") or "获取博主作品失败"
            if "NoneType" in detail or "不存在" in detail:
                detail = "账号不存在或作品接口暂时不可用"
            elif "x-rap-param" in detail:
                detail = "小红书风控限流，请稍后重试或更新 Cookie"
            raise HTTPException(status_code=502, detail=detail)
    else:
        raw_notes = notes_result.data or []

    total_notes = len(raw_notes)
    if source == "user_notes":
        from app.services.xhs_user_resolver import resolve_user_profile

        profile = await resolve_user_profile(crawler, user_id, nickname=nickname)
        total_notes = int(profile.get("note_count") or 0) or len(raw_notes)

    items = []
    for n in raw_notes[:limit]:
        if not isinstance(n, dict):
            continue
        n.setdefault("id", n.get("note_id", ""))
        note = normalize_note(n)
        # 作品列表接口只返回点赞数；搜索兜底才有完整互动数据
        note["full_stats"] = source == "search_fallback"
        items.append(note)

    if source == "user_notes" and nickname:
        # 用按昵称搜索的完整互动数据（评论/收藏/分享）按笔记 ID 合并，避免逐条抓详情
        search_result = await asyncio.to_thread(crawler.search_notes, nickname, limit=100)
        if search_result.success and search_result.data:
            search_stats: dict[str, dict] = {}
            for sn in search_result.data:
                if not isinstance(sn, dict):
                    continue
                sn.setdefault("id", sn.get("note_id", ""))
                norm = normalize_note(sn)
                search_stats[norm["platform_note_id"]] = norm["stats"]
            for item in items:
                st = search_stats.get(item["platform_note_id"])
                if st:
                    item["stats"]["collected"] = st.get("collected", 0)
                    item["stats"]["comments"] = st.get("comments", 0)
                    item["stats"]["shared"] = st.get("shared", 0)
                    item["full_stats"] = True
                    item["stats_source"] = "search"
        # 未命中搜索合并的笔记，抓详情补齐完整互动 / 时间 / 图片
        to_enrich = [i for i, item in enumerate(items) if not item.get("full_stats")][:enrich_limit]
        if to_enrich:
            await _enrich_note_details(items, to_enrich)
    payload = {"items": items, "total": total_notes, "user_id": user_id, "source": source}
    _search_cache_set(cache_key, payload)
    return payload


@router.post("/users/{user_id}/analysis")
async def analyze_user_notes_deprecated(
    user_id: str,
    body: UserAnalysisRequest | None = None,
    user: User = Depends(get_current_user),
):
    """[已下线] 同步分析接口：迁移到 POST /users/{user_id}/analysis-tasks。

    阶段 1：保留入口，记录访问日志并返回 410，观察一个发布周期确认零调用后
    阶段 2 物理删除（含 xhs_analysis.py 与 test_xhs_analysis.py）。
    """
    import logging

    logger = logging.getLogger("crawler.analysis_deprecated")
    logger.warning("deprecated sync analysis called user_id=%s nickname=%s", user_id, body.nickname if body else "")
    raise HTTPException(
        status_code=410,
        detail="该接口已下线，请改用 POST /api/v1/notes/users/{user_id}/analysis-tasks（异步任务）",
    )


class AnalysisTaskCreateRequest(BaseModel):
    nickname: str = ""
    fans: int = Field(0, ge=0)
    with_comments: bool = False


class AnalysisTaskBatchItem(BaseModel):
    user_id: str
    nickname: str = ""
    fans: int = Field(0, ge=0)
    with_comments: bool = False


class AnalysisTaskBatchRequest(BaseModel):
    bloggers: list[AnalysisTaskBatchItem] = Field(default_factory=list, min_length=1)


def _task_payload(task: BloggerAnalysisTask) -> dict:
    return {
        "id": str(task.id),
        "xhs_user_id": task.xhs_user_id,
        "nickname": str((task.result or {}).get("nickname") or ""),
        "follower_count": task.follower_count,
        "status": task.status,
        "prescreen_passed": task.prescreen_passed,
        "prescreen_reason": task.prescreen_reason,
        "total_notes": task.total_notes,
        "target_notes": task.target_notes,
        "fetched_notes": task.fetched_notes,
        "coverage": task.coverage,
        "confidence": task.confidence,
        "with_comments": task.with_comments,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


@router.post("/users/{user_id}/analysis-tasks", status_code=201)
async def create_analysis_task(
    user_id: str,
    body: AnalysisTaskCreateRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """真实数据版博主分析：先粗筛，通过后创建后台任务。"""
    from app.services.analysis_task_runner import prescreen_user, start_analysis_task

    prescreen = await prescreen_user(user_id)
    if not prescreen["passed"]:
        return {
            "passed_prescreen": False,
            "reason": prescreen["reason"],
            "fans": prescreen.get("fans", 0),
            "notes": prescreen.get("notes", 0),
            "avg_likes": prescreen.get("avg_likes", 0.0),
        }
    task = BloggerAnalysisTask(
        user_id=user.id,
        xhs_user_id=user_id,
        status="pending",
        prescreen_passed=True,
        follower_count=prescreen.get("fans", 0) or 0,
        total_notes=prescreen.get("notes", 0) or 0,
        with_comments=bool(body.with_comments if body else False),
    )
    db.add(task)
    await db.flush()
    # 先提交让后台任务能看到刚插入的任务行，否则 run_analysis_task 可能抢在提交前
    # 读取并返回 None，导致任务永远停留在 pending
    await db.commit()
    start_analysis_task(task.id)
    payload = _task_payload(task)
    payload["passed_prescreen"] = True
    return payload


@router.post("/analysis-tasks/batch")
async def create_analysis_tasks_batch(
    body: AnalysisTaskBatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量真实分析：逐博主串行真实列表粗筛，通过者创建后台任务（上限 50）。

    粗筛异常按博主隔离；DB 写入失败整批回滚（原子）。重复 user_id 只处理首个。
    """
    from app.services.analysis_task_runner import prescreen_user, start_analysis_task

    if not body.bloggers:
        raise HTTPException(status_code=422, detail="批量分析至少需要 1 个博主")
    if len(body.bloggers) > 50:
        raise HTTPException(status_code=422, detail="批量分析单次最多 50 个博主")

    # 去重（first-wins）：重复 user_id 不重复粗筛、不重复建任务
    seen: set[str] = set()
    bloggers: list[AnalysisTaskBatchItem] = []
    for b in body.bloggers:
        if b.user_id in seen:
            continue
        seen.add(b.user_id)
        bloggers.append(b)

    created: list[dict] = []
    rejected: list[dict] = []
    created_task_ids: list[uuid.UUID] = []
    for b in bloggers:
        try:
            result = await prescreen_user(b.user_id)
        except Exception as exc:
            logger.warning("批量粗筛异常 user=%s: %s", b.user_id, exc)
            # 单个博主粗筛异常不中断整批，按拒绝处理
            rejected.append(
                {
                    "xhs_user_id": b.user_id,
                    "nickname": b.nickname or "",
                    "reason": "粗筛异常",
                }
            )
            continue
        if not result["passed"]:
            rejected.append(
                {
                    "xhs_user_id": b.user_id,
                    "nickname": b.nickname or "",
                    "reason": result.get("reason") or "未通过粗筛",
                }
            )
            continue
        task = BloggerAnalysisTask(
            user_id=user.id,
            xhs_user_id=b.user_id,
            status="pending",
            prescreen_passed=True,
            prescreen_reason=None,
            follower_count=result.get("fans") or b.fans,
            total_notes=result.get("notes", 0) or 0,
            with_comments=b.with_comments,
        )
        db.add(task)
        await db.flush()
        created_task_ids.append(task.id)
        created.append(
            {
                "task_id": str(task.id),
                "xhs_user_id": b.user_id,
                "nickname": b.nickname or "",
                "status": "pending",
                "follower_count": task.follower_count,
                "notes": task.total_notes,
            }
        )
    # 先提交让后台任务能看到刚插入的任务行，再逐个调度（与单号分析一致）
    await db.commit()
    for task_id in created_task_ids:
        start_analysis_task(task_id)
    return {"created": created, "rejected": rejected}


@router.get("/analysis-tasks")
async def list_analysis_tasks(
    status: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只读列表：供批量筛选视图拉取成功/部分结果，按完成时间倒序。"""
    stmt = select(BloggerAnalysisTask).where(BloggerAnalysisTask.user_id == user.id)
    if status:
        stmt = stmt.where(BloggerAnalysisTask.status == status)
    stmt = stmt.order_by(BloggerAnalysisTask.finished_at.desc().nulls_last()).limit(min(max(limit, 1), 500))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_task_payload(t) for t in rows]}


@router.get("/users/{user_id}/analysis-tasks/{task_id}")
async def get_analysis_task(
    user_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(BloggerAnalysisTask).where(BloggerAnalysisTask.id == tid, BloggerAnalysisTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    return _task_payload(task)


@router.delete("/users/{user_id}/analysis-tasks/{task_id}")
async def cancel_analysis_task(
    user_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.analysis_task_runner import cancel_task

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(BloggerAnalysisTask).where(BloggerAnalysisTask.id == tid, BloggerAnalysisTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    if task.status in ("pending", "running"):
        task.status = "cancelled"
        cancel_task(tid)
        await db.flush()
    return _task_payload(task)


class SearchNotesRequest(BaseModel):
    query: str
    limit: int = Field(20, ge=1, le=100)
    sort: int = Field(0, ge=0, le=4)
    note_type: int = Field(0, ge=0, le=2)
    time_range: int = Field(0, ge=0, le=3)


@router.post("/search")
async def search_notes(
    body: SearchNotesRequest,
    user: User = Depends(get_current_user),
):
    """搜索小红书笔记，返回标准化结果。"""
    sort_map = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}
    sort_choice = sort_map.get(body.sort, 0)
    crawler = _get_crawler()
    result = await asyncio.to_thread(
        crawler.search_notes,
        body.query, limit=body.limit,
        sort_type=sort_choice, note_type=body.note_type, time_range=body.time_range,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "搜索失败")
    payload = {"items": [normalize_note(n) for n in result.data], "stats": result.stats}
    cache_key = f"search:{body.query}:{body.limit}:{body.sort}:{body.note_type}:{body.time_range}"
    _search_cache_set(cache_key, payload)
    return payload


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
    result = await asyncio.to_thread(crawler.get_note_detail, url)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "获取失败")
    items = _extract_detail_items(result)
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
    result = await asyncio.to_thread(crawler.get_comments, url)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "获取失败")
    return {"items": [normalize_comment(c, note_id) for c in result.data]}

