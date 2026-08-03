"""门店 Pydantic schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ShopCreate(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    category: str | None = None


class ShopUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    category: str | None = None
    status: str | None = None


class ShopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    name: str
    address: str | None = None
    phone: str | None = None
    category: str | None = None
    status: str
    created_at: datetime
