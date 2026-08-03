"""爬虫任务 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.user import User

from crawler import tasks

router = APIRouter(prefix="/crawl-jobs", tags=["crawl"])


class CreateCrawlJobRequest(BaseModel):
    job_type: str
    params: dict


@router.post("")
async def create_crawl_job(
    body: CreateCrawlJobRequest,
    current_user: User = Depends(get_current_user),
):
    job_id = tasks.dispatch_job(body.job_type, body.params)
    return {"job_id": job_id, "status": "running"}


@router.get("")
async def list_crawl_jobs(
    current_user: User = Depends(get_current_user),
):
    running = tasks.list_tasks()
    return {"running": running}


@router.get("/{job_id}")
async def get_crawl_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = tasks.get_task(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
