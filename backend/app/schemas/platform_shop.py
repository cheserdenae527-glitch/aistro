"""平台店铺 Pydantic schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlatformShopCreate(BaseModel):
    platform: str
    platform_shop_id: str | None = None
    shop_url: str | None = None
    shop_name: str | None = None


class PlatformShopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    platform: str
    platform_shop_id: str | None = None
    shop_url: str | None = None
    shop_name: str | None = None
    rating: float | None = None
    monthly_sales: int | None = None
    total_reviews: int | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
