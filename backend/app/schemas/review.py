"""口碑管理模块 Pydantic Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_shop_id: uuid.UUID
    platform_review_id: str | None = None
    reviewer_name: str | None = None
    rating: int | None = None
    content: str | None = None
    tags: list | None = None
    sentiment: str | None = None
    reply_status: str | None = None
    ai_reply: str | None = None
    reply_content: str | None = None
    replied_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_type: str
    parent_review_id: uuid.UUID | None = None
    note_title: str | None = None
    note_url: str | None = None
    author_id: str | None = None
    author_avatar: str | None = None
    interact_stats: dict | None = None
    source_json: dict | None = None
    alert_status: str
    alert_reason: dict | None = None
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int
    size: int


class SyncXiaohongshuRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(20, ge=1, le=50)


class SyncResponse(BaseModel):
    created: int
    skipped: int


class BatchAnalyzeRequest(BaseModel):
    review_ids: list[uuid.UUID] = Field(..., min_length=1)


class BatchAnalyzeItem(BaseModel):
    id: uuid.UUID
    sentiment: str
    tags: list[str] = Field(default_factory=list)


class BatchAnalyzeResponse(BaseModel):
    analyzed: list[BatchAnalyzeItem]
    failed: list[uuid.UUID]
    total: int
    success_count: int
    failed_count: int


class AiReplyResponse(BaseModel):
    id: uuid.UUID
    ai_reply: str
    reply_status: str = "ai_replied"


class ReplyUpdateRequest(BaseModel):
    reply_content: str = Field(..., min_length=1, max_length=5000)


class AlertAckResponse(BaseModel):
    id: uuid.UUID
    alert_status: str


class ReputationSummaryResponse(BaseModel):
    note_count: int
    comment_count: int
    rating_review_count: int
    sentiment_counts: dict[str, int]
    unreplied_count: int
    alert_count: int
