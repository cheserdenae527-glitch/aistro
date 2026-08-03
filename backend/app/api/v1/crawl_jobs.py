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
    if body.job_type not in tasks.VALID_JOB_TYPES:
        raise HTTPException(status_code=400, detail="未知任务类型")
    error = tasks.validate_job_params(body.job_type, body.params)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if tasks.active_count(str(current_user.id)) >= 20:
        raise HTTPException(status_code=429, detail="运行中的任务过多，请稍后再试")
    job_id = tasks.dispatch_job(body.job_type, body.params, str(current_user.id))
    return {"job_id": job_id, "status": "running"}


@router.get("")
async def list_crawl_jobs(
    current_user: User = Depends(get_current_user),
):
    running = tasks.list_tasks(str(current_user.id))
    return {"running": running}


@router.get("/{job_id}")
async def get_crawl_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = tasks.get_task(job_id, str(current_user.id))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
