"""设置相关 Pydantic schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ApiKeyUpdate(BaseModel):
    """None = 保持不变；空字符串 = 清空密钥。"""

    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)


class SettingsUpdate(BaseModel):
    storage_dir: str | None = Field(default=None, max_length=1024)
    text: ApiKeyUpdate | None = None
    image: ApiKeyUpdate | None = None
    vision: ApiKeyUpdate | None = None
    video: ApiKeyUpdate | None = None


class ApiKeyStatus(BaseModel):
    configured: bool
    preview: str | None = None
    base_url: str
    model: str


class SettingsResponse(BaseModel):
    storage: dict
    text: ApiKeyStatus
    image: ApiKeyStatus
    vision: ApiKeyStatus
    video: ApiKeyStatus