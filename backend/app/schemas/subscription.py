"""订阅 Pydantic schema。"""
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

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
    last_crawled_at: datetime | None = None
    created_at: datetime

class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    note_count: int
    follower_count: int
    following_count: int
    crawled_at: datetime
