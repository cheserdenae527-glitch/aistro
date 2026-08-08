"""订阅 Pydantic schema。"""
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class SubscriptionCreate(BaseModel):
    xhs_user_id: str
    nickname: str
    avatar: str | None = None

class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    xhs_user_id: str
    nickname: str
    avatar: str | None = None
    note_count: int
    follower_count: int
    following_count: int
    notified_note_count: int = 0
    last_crawled_at: datetime | None = None
    created_at: datetime
    refresh_status: str | None = None
    refresh_error: str | None = None


class SubscriptionStatusItem(BaseModel):
    subscribed: bool
    subscription_id: uuid.UUID | None = None
    has_update: bool = False


class SubscriptionStatusBatchRequest(BaseModel):
    xhs_user_ids: list[str] = Field(..., max_length=50)


class SubscriptionStatusBatchResponse(BaseModel):
    items: dict[str, SubscriptionStatusItem]

class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    note_count: int
    follower_count: int
    following_count: int
    crawled_at: datetime
