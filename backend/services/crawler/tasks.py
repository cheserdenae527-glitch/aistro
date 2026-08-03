"""
爬虫任务运行器。使用 threading 在后台执行爬虫任务。
当 Redis/Celery 可用时可切换为 RQ/Celery worker。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

# 内存任务状态（生产环境换 Redis）
_task_store: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# 导入爬虫
from crawler.xhs import XhsCrawler

# XHSCookie（从 payload_user.json 读取，生产环境存入数据库配置）
import os
_COOKIE_PATH = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "payload_user.json")
_XHS_COOKIE: str | None = None


def _load_cookie() -> str:
    global _XHS_COOKIE
    if _XHS_COOKIE:
        return _XHS_COOKIE
    with open(_COOKIE_PATH, "r") as f:
        _XHS_COOKIE = json.load(f)["cookies_str"]
    return _XHS_COOKIE


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        return _task_store.get(task_id)


def list_tasks() -> list[dict[str, Any]]:
    with _lock:
        return list(_task_store.values())


# ── 任务定义 ──

def run_search_job(job_id: str, query: str, limit: int = 20, sort_type: int = 0, note_type: int = 0, time_range: int = 0, proxies: dict | None = None):
    """搜索笔记任务。"""
    cookie = _load_cookie()
    crawler = XhsCrawler(cookie, proxies=proxies)
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
    cookie = _load_cookie()
    crawler = XhsCrawler(cookie, proxies=proxies)
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
    cookie = _load_cookie()
    crawler = XhsCrawler(cookie, proxies=proxies)
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


def dispatch_job(job_type: str, params: dict) -> str:
    """创建并调度一个爬虫任务。返回 job_id。"""
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "type": job_type,
        "params": params,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
    }
    with _lock:
        _task_store[job_id] = job

    runner = _TASK_DISPATCH.get(job_type)
    if runner:
        t = threading.Thread(target=runner, args=(job_id,), kwargs=params, daemon=True)
        t.start()
    else:
        with _lock:
            job["status"] = "failed"
            job["result"] = {"error": f"Unknown job type: {job_type}"}

    return job_id


