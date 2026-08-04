"""内容工坊模块 Pydantic Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sensitive_filter import contains_blocked


def _check_no_blocked(v: str | None) -> str | None:
    if v is not None and contains_blocked(v):
        raise ValueError("文本包含敏感词")
    return v


# ============================================================
# 项目
# ============================================================


class StudioProjectCreate(BaseModel):
    shop_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def title_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class StudioProjectUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    status: Literal["draft", "generated"] | None = None

    @field_validator("title")
    @classmethod
    def title_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class StudioProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class StudioCopySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    input_payload: dict | None = None
    titles: list | None = None
    body: str | None = None
    tags: list | None = None
    image_guide: dict | None = None
    created_at: datetime


class StudioDeckSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    copy_id: uuid.UUID
    template: str
    theme: str
    page_count: int
    page_specs: list | None = None
    source_assets: list | None = None
    images: list | None = None
    qa_report: dict | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class StudioProjectDetail(StudioProjectResponse):
    copies: list[StudioCopySummary] = []
    decks: list[StudioDeckSummary] = []


# ============================================================
# 文案
# ============================================================


class CopyGenerateRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    style: str = Field(..., min_length=1, max_length=50)
    price_range: str = Field(..., min_length=1, max_length=50)
    topic: str = Field(..., min_length=1, max_length=200)
    shop_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("category", "style", "price_range", "topic", "shop_name")
    @classmethod
    def no_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class CopyTitleItem(BaseModel):
    text: str = Field(..., max_length=50)
    strategy: str = Field(..., max_length=50)


class ImageGuidePage(BaseModel):
    position: str = Field(..., max_length=100)
    purpose: str = Field(..., max_length=100)
    prompt: str = Field(..., max_length=2000)


class CopyImageGuide(BaseModel):
    cover_prompt: str = Field(..., max_length=2000)
    pages: list[ImageGuidePage] = []


class CopyGenerateResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    input_payload: dict
    titles: list[CopyTitleItem]
    body: str
    tags: list[str]
    image_guide: CopyImageGuide
    created_at: datetime


class CopyUpdateRequest(BaseModel):
    titles: list[CopyTitleItem] | None = None
    body: str | None = Field(None, min_length=1, max_length=5000)
    tags: list[str] | None = None
    image_guide: CopyImageGuide | None = None

    @field_validator("body")
    @classmethod
    def body_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


# ============================================================
# 卡组
# ============================================================


class DeckCreateRequest(BaseModel):
    copy_id: uuid.UUID
    template: Literal["editorial", "swiss"]
    theme: str = Field(..., min_length=1, max_length=50)
    page_count: int
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)


class DeckCreateResponse(BaseModel):
    deck_id: uuid.UUID
    images: list[dict] = []
    qa_report: dict | None = None
    status: str
    error_message: str | None = None


class ExportToDesignResponse(BaseModel):
    design_project_id: uuid.UUID
    asset_ids: list[uuid.UUID]
# ============================================================
# 配图提示词丰富
# ============================================================


class ImagePromptEnrichRequest(BaseModel):
    direction: str = Field(..., min_length=1, max_length=500)

    @field_validator("direction")
    @classmethod
    def direction_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class ImagePromptEnrichResponse(BaseModel):
    main_idea: str
    prompt: str
