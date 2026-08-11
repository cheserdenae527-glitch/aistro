"""
爬虫任务运行器。使用 threading 在后台执行爬虫任务。
当 Redis/Celery 可用时可切换为 RQ/Celery worker。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

# 内存任务状态（生产环境换 Redis）
_task_store: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# 导入爬虫
from crawler.xhs import XhsCrawler
from crawler.config import acquire_cookie


def get_task(task_id: str, user_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _task_store.get(task_id)
        if job and job.get("user_id") == user_id:
            return job
        return None


def list_tasks(user_id: str) -> list[dict[str, Any]]:
    with _lock:
        return [job for job in _task_store.values() if job.get("user_id") == user_id]


# ── 任务定义 ──

def _build_crawler(cookie: str, sticky_pool: list[dict] | None, cookie_id: str | None = None, proxies: dict | None = None) -> XhsCrawler:
    """创建使用粘性代理池的爬虫；Cookie 池 id 用于健康度回写。"""
    pool = list(sticky_pool or [])
    if proxies:
        pool = [proxies] + [p for p in pool if p != proxies]
    return XhsCrawler(
        cookie,
        proxy_pool=pool or None,
        cookie_id=cookie_id,
    )


def run_search_job(job_id: str, query: str, limit: int = 20, sort_type: int = 0, note_type: int = 0, time_range: int = 0, proxies: dict | None = None):
    """搜索笔记任务。"""
    cookie, cookie_id, sticky_pool = acquire_cookie()
    crawler = _build_crawler(cookie, sticky_pool, cookie_id, proxies)
    result = crawler.search_notes(query, limit=limit, sort_type=sort_type, note_type=note_type, time_range=time_range)
    with _lock:
        job = _task_store.get(job_id)
        if job:
            job["status"] = "success" if result.success else "failed"
            job["result"] = {
                "data": result.data,
                "error": result.error,
                "stats": result.stats,
            }
            job["finished_at"] = datetime.now(timezone.utc).isoformat()


def run_note_detail_job(job_id: str, note_url: str, proxies: dict | None = None):
    """笔记详情任务。"""
    cookie, cookie_id, sticky_pool = acquire_cookie()
    crawler = _build_crawler(cookie, sticky_pool, cookie_id, proxies)
    result = crawler.get_note_detail(note_url)
    with _lock:
        job = _task_store.get(job_id)
        if job:
            job["status"] = "success" if result.success else "failed"
            job["result"] = {
                "data": result.data,
                "error": result.error,
                "stats": result.stats,
            }
            job["finished_at"] = datetime.now(timezone.utc).isoformat()


def run_comment_job(job_id: str, note_url: str, proxies: dict | None = None):
    """评论抓取任务。"""
    cookie, cookie_id, sticky_pool = acquire_cookie()
    crawler = _build_crawler(cookie, sticky_pool, cookie_id, proxies)
    result = crawler.get_comments(note_url)
    with _lock:
        job = _task_store.get(job_id)
        if job:
            job["status"] = "success" if result.success else "failed"
            job["result"] = {
                "data": result.data,
                "error": result.error,
                "stats": result.stats,
            }
            job["finished_at"] = datetime.now(timezone.utc).isoformat()


# ── 调度器 ──

_TASK_DISPATCH = {
    "search": run_search_job,
    "note_detail": run_note_detail_job,
    "comment": run_comment_job,
}


VALID_JOB_TYPES = frozenset(_TASK_DISPATCH)


def validate_job_params(job_type: str, params: dict) -> str | None:
    """返回错误信息，参数合法时返回 None。"""
    if job_type == "search":
        if not str(params.get("query", "")).strip():
            return "query is required"
        limit = params.get("limit", 20)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            return "limit must be between 1 and 100"
    elif job_type in ("note_detail", "comment"):
        note_url = str(params.get("note_url", ""))
        if not note_url.startswith(("http://", "https://")):
            return "note_url is required"
    return None


def active_count(user_id: str) -> int:
    with _lock:
        return sum(
            1
            for job in _task_store.values()
            if job.get("user_id") == user_id and job.get("status") == "running"
        )


def _run_job_safely(job_id: str, runner, **params) -> None:
    try:
        runner(job_id, **params)
    except Exception as e:
        with _lock:
            job = _task_store.get(job_id)
            if job:
                job["status"] = "failed"
                job["result"] = {"error": str(e)}
                job["finished_at"] = datetime.now(timezone.utc).isoformat()


def dispatch_job(job_type: str, params: dict, user_id: str) -> str:
    """创建并调度一个爬虫任务。返回 job_id。"""
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": job_type,
        "params": params,
        "user_id": user_id,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
    }
    with _lock:
        _task_store[job_id] = job

    runner = _TASK_DISPATCH.get(job_type)
    if runner:
        t = threading.Thread(
            target=_run_job_safely,
            args=(job_id, runner),
            kwargs=params,
            daemon=True,
        )
        t.start()
    else:
        with _lock:
            job["status"] = "failed"
            job["result"] = {"error": f"Unknown job type: {job_type}"}

    return job_id


