"""商家 Pydantic schema。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MerchantCreate(BaseModel):
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    tier: str = "trial"
    notes: str | None = None


class MerchantUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    tier: str | None = None
    notes: str | None = None


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    tier: str
    notes: str | None = None
    created_at: datetime
