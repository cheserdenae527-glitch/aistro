"""视觉设计模块 Pydantic Schema。"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sensitive_filter import contains_blocked


def _strip_data_url(value: str) -> str:
    if "," in value and value.startswith("data:"):
        return value.split(",", 1)[1]
    return value


def _decode_size(value: str) -> int:
    return len(base64.b64decode(_strip_data_url(value)))


# ============================================================
# 设计项目
# ============================================================


class DesignProjectCreate(BaseModel):
    shop_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=100)
    status: Literal["draft", "active", "archived"] = "draft"


class DesignProjectUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    status: Literal["draft", "active", "archived"] | None = None


class DesignProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


# ============================================================
# 素材
# ============================================================


class DesignAssetUpdate(BaseModel):
    asset_type: Literal["dish", "logo", "photo"] | None = None
    dish_name: str | None = Field(None, max_length=200)
    price: Decimal | None = None
    tagline: str | None = Field(None, max_length=200)

    @field_validator("dish_name", "tagline")
    @classmethod
    def no_blocked_text(cls, v: str | None) -> str | None:
        if v is not None and contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class DesignAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    asset_type: str
    source: str
    status: str
    batch_id: uuid.UUID | None = None
    derived_from_asset_id: uuid.UUID | None = None
    original_url: str | None = None
    processed_url: str | None = None
    thumb_url: str | None = None
    edit_stack: list | None = None
    beauty_config: dict | None = None
    dish_name: str | None = None
    price: Decimal | None = None
    tagline: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetCandidate(BaseModel):
    aid: uuid.UUID
    url: str
    thumb_url: str | None = None
    batch_id: uuid.UUID


class GenerateCandidatesResponse(BaseModel):
    batch_id: uuid.UUID
    candidates: list[AssetCandidate]


class ConfirmResponse(BaseModel):
    batch_id: uuid.UUID
    active_aid: uuid.UUID
    discarded_aids: list[uuid.UUID]


class BeautifyRequest(BaseModel):
    mode: Literal["enhance", "color_correct"] = "enhance"
    brightness: float = Field(1.05, ge=0.5, le=2.0)
    contrast: float = Field(1.08, ge=0.5, le=2.0)
    saturation: float = Field(1.05, ge=0.5, le=2.0)


class EditRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def prompt_blocked_check(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("prompt 包含敏感词")
        return v


class AiBeautifyRequest(BaseModel):
    """AI 一键美化 — prompt 可选，后端提供默认增强方向。"""

    prompt: str | None = Field(None, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def prompt_blocked_check(cls, v: str | None) -> str | None:
        if v is not None and contains_blocked(v):
            raise ValueError("prompt 包含敏感词")
        return v


class BeautifyPromptRequest(BaseModel):
    """AI 编辑提示词生成 — kind 支持 ai/bg/enhance，focus 表明侧重点。"""

    kind: Literal["ai", "bg", "enhance"] = "ai"
    focus: str | None = Field(None, max_length=100)
    dish_name: str | None = Field(None, max_length=200)

    @field_validator("focus", "dish_name")
    @classmethod
    def no_blocked_text(cls, v: str | None) -> str | None:
        if v is not None and contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class BeautifyPromptResponse(BaseModel):
    prompt: str


class SaveRequest(BaseModel):
    image_base64: str = Field(..., min_length=1)
    edit_stack: list | None = None
    beauty_config: dict | None = None

    @field_validator("image_base64")
    @classmethod
    def check_size_after_decode(cls, v: str) -> str:
        try:
            decoded_len = _decode_size(v)
        except Exception:
            raise ValueError("无效的 base64 编码")
        if decoded_len > 10 * 1024 * 1024:
            raise ValueError("图片大小超过 10MB 限制")
        return v


# ============================================================
# 菜单
# ============================================================


class MenuColorScheme(BaseModel):
    primary: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    text: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    preset_name: str | None = None


class MenuItemInput(BaseModel):
    asset_id: uuid.UUID
    section: str = Field("招牌", max_length=50)
    sort: int = Field(0, ge=0)
    override_name: str | None = Field(None, max_length=200)
    override_price: Decimal | None = None
    override_tagline: str | None = Field(None, max_length=200)

    @field_validator("override_name", "override_tagline")
    @classmethod
    def no_blocked_text(cls, v: str | None) -> str | None:
        if v is not None and contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class MenuCreate(BaseModel):
    menu_type: Literal["xhs", "a4"] = "xhs"
    template_id: str = Field("xhs_menu_01", max_length=50)
    shop_name: str | None = Field(None, max_length=100)
    logo_url: str | None = None
    color_scheme: MenuColorScheme | None = None
    items: list[MenuItemInput] = Field(default_factory=list)


class MenuUpdate(BaseModel):
    version: int
    menu_type: Literal["xhs", "a4"] | None = None
    template_id: str | None = Field(None, max_length=50)
    shop_name: str | None = Field(None, max_length=100)
    logo_url: str | None = None
    color_scheme: MenuColorScheme | None = None
    items: list[MenuItemInput] | None = None


class MenuResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    menu_type: str
    template_id: str
    shop_name: str | None = None
    logo_url: str | None = None
    color_scheme: dict | None = None
    items: list | None = None
    output_url: str | None = None
    output_pages: list[str] | None = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class RenderRequest(BaseModel):
    version: int


class RenderResponse(BaseModel):
    id: uuid.UUID
    output_url: str
    pages: list[str] | None = None
    status: str = "rendered"
    version: int


class PdfExportResponse(BaseModel):
    id: uuid.UUID
    output_url: str
    version: int


# ============================================================
# 后台任务 / 菜单历史版本
# ============================================================


class DesignJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: str
    batch_id: uuid.UUID | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DesignJobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str = "pending"


class MenuVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_id: uuid.UUID
    version: int
    snapshot: dict
    created_at: datetime


class RestoreVersionRequest(BaseModel):
    version: int
