"""团购工坊模块 Pydantic Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sensitive_filter import contains_blocked

Platform = Literal["douyin", "meituan", "xiaohongshu"]
ItemCategory = Literal["signature", "staple", "snack", "drink"]
SchemeType = Literal["hook", "profit", "scenario"]


def _check_no_blocked(v: str | None) -> str | None:
    if v is not None and contains_blocked(v):
        raise ValueError("文本包含敏感词")
    return v


# ============================================================
# 项目
# ============================================================


class DealProjectCreate(BaseModel):
    shop_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=100)
    platform: Platform = "douyin"
    price_band: str | None = Field(None, max_length=50)

    @field_validator("title", "price_band")
    @classmethod
    def title_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class DealProjectUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    platform: Platform | None = None
    price_band: str | None = Field(None, max_length=50)

    @field_validator("title", "price_band")
    @classmethod
    def title_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class DealProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    title: str
    platform: str
    price_band: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class DealProjectListResponse(BaseModel):
    items: list[DealProjectResponse]
    total: int
    page: int
    size: int


# ============================================================
# 菜品清单
# ============================================================


class DealItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: ItemCategory = "staple"
    cost_price: Decimal | None = Field(None, ge=0)
    sale_price: Decimal = Field(..., gt=0)
    is_signature: bool = False
    is_high_margin: bool = False
    image_url: str | None = Field(None, max_length=2000)

    @field_validator("name")
    @classmethod
    def name_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class DealItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    category: ItemCategory | None = None
    cost_price: Decimal | None = Field(None, ge=0)
    sale_price: Decimal | None = Field(None, gt=0)
    is_signature: bool | None = None
    is_high_margin: bool | None = None
    image_url: str | None = Field(None, max_length=2000)

    @field_validator("name")
    @classmethod
    def name_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class DealItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    category: str
    cost_price: Decimal | None = None
    sale_price: Decimal
    is_signature: bool
    is_high_margin: bool
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class DealItemListResponse(BaseModel):
    items: list[DealItemOut]
    total: int
    page: int
    size: int


# ============================================================
# 竞品套餐
# ============================================================


class CompetitorDealCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0)
    items_summary: str = Field(..., min_length=1, max_length=2000)
    note: str | None = Field(None, max_length=2000)

    @field_validator("name", "items_summary", "note")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class CompetitorDealUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    price: Decimal | None = Field(None, gt=0)
    items_summary: str | None = Field(None, min_length=1, max_length=2000)
    note: str | None = Field(None, max_length=2000)

    @field_validator("name", "items_summary", "note")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class CompetitorDealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    price: Decimal
    items_summary: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class CompetitorDealListResponse(BaseModel):
    items: list[CompetitorDealOut]
    total: int
    page: int
    size: int


# ============================================================
# 套餐方案
# ============================================================


class SchemeItemIn(BaseModel):
    item_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    qty: int = Field(..., ge=1, le=99)
    sale_price: Decimal | None = Field(None, gt=0)
    cost_price: Decimal | None = Field(None, ge=0)

    @field_validator("name")
    @classmethod
    def name_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class DealCopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scheme_id: uuid.UUID
    platform: str
    title: str
    selling_points: list | None = None
    rules: str | None = None
    cover_prompt: str | None = None
    created_at: datetime
    updated_at: datetime


class DealSchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    scheme_type: str
    generation_batch: int
    title: str
    description: str | None = None
    items: list | None = None
    original_price: Decimal
    deal_price: Decimal
    cost_estimate: Decimal | None = None
    margin_estimate: dict | None = None
    status: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    copies: list[DealCopyOut] = []


class SchemeUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    items: list[SchemeItemIn] | None = None
    original_price: Decimal | None = Field(None, gt=0)
    deal_price: Decimal | None = Field(None, gt=0)
    cost_estimate: Decimal | None = Field(None, ge=0)
    margin_estimate: dict | None = None

    @field_validator("title", "description")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class SchemeGenerateResponse(BaseModel):
    generation_batch: int
    schemes: list[DealSchemeOut]


# ============================================================
# 平台文案 / 导出
# ============================================================


class DealCopyGenerateRequest(BaseModel):
    platform: Platform


class DealCopyUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    selling_points: list[str] | None = Field(None, max_length=8)
    rules: str | None = Field(None, max_length=2000)
    cover_prompt: str | None = Field(None, max_length=2000)

    @field_validator("title", "rules", "cover_prompt")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)

    @field_validator("selling_points")
    @classmethod
    def points_blocked(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for point in v:
                if contains_blocked(point):
                    raise ValueError("文本包含敏感词")
        return v


class ExportToDesignRequest(BaseModel):
    platform: Platform


class ExportToDesignResponse(BaseModel):
    design_project_id: uuid.UUID
    asset_ids: list[uuid.UUID]



