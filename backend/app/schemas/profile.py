"""装修模块 Pydantic Schema — 含 emoji 过滤、字数校验、敏感词校验。"""
from __future__ import annotations

import re as std_re
import uuid
from datetime import datetime
from typing import Literal

import regex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.sensitive_filter import contains_blocked


# ============================================================
# 色系 Schema
# ============================================================

COLOR_HEX_RE = std_re.compile(r"^#[0-9A-Fa-f]{6}$")


class ColorScheme(BaseModel):
    primary: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    text: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    preset_name: str | None = None


class ColorSchemePreset(BaseModel):
    name: str
    primary: str
    secondary: str
    accent: str
    text: str
    description: str | None = None


class ImageOption(BaseModel):
    object_name: str  # MinIO object 路径，用于后续选择
    url: str


# ============================================================
# Profile 读写
# ============================================================

_EMOJI_PATTERN = regex.compile(r"\p{Extended_Pictographic}")


class ProfileUpdate(BaseModel):
    """PUT /profiles — 保存草稿。version 强制。"""

    nickname: str | None = Field(None, max_length=20)
    bio: str | None = Field(None, max_length=100)
    avatar_gen_prompt: str | None = Field(None, max_length=1000)
    bg_gen_prompt: str | None = Field(None, max_length=1000)
    color_primary: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_secondary: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_accent: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_text: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_mode: str | None = Field(None, pattern=r"^(preset|custom)$")
    color_preset_name: str | None = None
    version: int

    @field_validator("nickname")
    @classmethod
    def nickname_no_emoji(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _EMOJI_PATTERN.search(v):
            raise ValueError("昵称不允许包含 emoji")
        if contains_blocked(v):
            raise ValueError("昵称包含敏感词")
        return v

    @field_validator("bio")
    @classmethod
    def bio_blocked_check(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if contains_blocked(v):
            raise ValueError("简介包含敏感词")
        return v


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    platform: str
    nickname: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    avatar_original_url: str | None = None
    avatar_gen_prompt: str | None = None
    avatar_options: list["ImageOption"] | None = None
    bg_image_url: str | None = None
    bg_original_url: str | None = None
    bg_gen_prompt: str | None = None
    bg_options: list["ImageOption"] | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    color_accent: str | None = None
    color_text: str | None = None
    color_mode: str | None = None
    color_preset_name: str | None = None
    ai_input_category: str | None = None
    ai_input_style: str | None = None
    ai_input_price: str | None = None
    ai_variants: dict | None = None
    health_check: dict | None = None
    bio_flagged: bool = False
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


# ============================================================
# AI 生成
# ============================================================

class GenerateRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    style: str = Field(..., min_length=1, max_length=200)
    price_range: str = Field("人均80", max_length=50)

    @field_validator("category", "style")
    @classmethod
    def no_blocked_prompt(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("输入包含敏感词")
        return v


class VariantColorScheme(BaseModel):
    primary: str
    secondary: str
    accent: str
    text: str
    preset_name: str | None = None


class AiVariant(BaseModel):
    id: str  # "A", "B", "C", "D"
    color_scheme: VariantColorScheme
    nickname_options: list[str] = Field(..., max_length=3)
    bio: str
    avatar_prompt: str
    bg_prompt: str
    filtered: bool = False
    bio_flagged: bool = False


class GenerateResponse(BaseModel):
    variants: list[AiVariant]
    generated_at: datetime


# ============================================================
# 图片生成
# ============================================================

class ImageGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def prompt_blocked_check(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("prompt 包含敏感词")
        return v


class ImageGenerateResponse(BaseModel):
    url: str  # MinIO URL（original_url）
    prompt: str


class ImageGenerateOptionsResponse(ImageGenerateResponse):
    options: list[ImageOption]


class SelectImageRequest(BaseModel):
    object_name: str = Field(..., min_length=1)


class PromptGenerateRequest(BaseModel):
    section: Literal["avatar", "bg"]
    category: str = Field(..., min_length=1, max_length=50)
    style: str = Field(..., min_length=1, max_length=200)
    price_range: str = Field("人均80", max_length=50)

    @field_validator("category", "style")
    @classmethod
    def no_blocked_prompt(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("输入包含敏感词")
        return v


class PromptGenerateResponse(BaseModel):
    section: Literal["avatar", "bg"]
    prompt: str


class HealthCheckRequest(BaseModel):
    nickname: str = ""
    bio: str = ""
    avatar_prompt: str = ""
    bg_prompt: str = ""
    color_primary: str | None = None
    color_secondary: str | None = None
    color_accent: str | None = None
    color_text: str | None = None
    has_avatar: bool = False
    has_bg: bool = False


class HealthCheckResponse(BaseModel):
    first_impression: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    checked_at: datetime


class RemoveGalleryImageRequest(BaseModel):
    section: Literal["avatar", "bg"]
    object_name: str = Field(..., min_length=1)


# ============================================================
# 图片裁剪
# ============================================================

class CropRequest(BaseModel):
    image_base64: str = Field(..., min_length=1)

    @field_validator("image_base64")
    @classmethod
    def check_size_after_decode(cls, v: str) -> str:
        """base64 解码后不超过 10MB。"""
        import base64

        # 去除可能的 data:xxx;base64, 前缀
        if "," in v and v.startswith("data:"):
            v = v.split(",", 1)[1]
        try:
            decoded_len = len(base64.b64decode(v))
        except Exception:
            raise ValueError("无效的 base64 编码")
        if decoded_len > 10 * 1024 * 1024:
            raise ValueError("图片大小超过 10MB 限制")
        return v


class CropResponse(BaseModel):
    url: str  # 裁剪后 URL
