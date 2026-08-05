"""直播工坊数字人形象模型（团队级共享，org 维度）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveAvatar(Base):
    """数字人形象库。

    org_id 说明（SPEC §4/§10）：当前系统尚无 org/租户模型（只有
    user -> merchant -> shop 绑定关系），MVP 阶段按 SPEC 退化映射为
    "创建该形象的用户所绑定的主账号 ID"（即 users.id）：同一账号下的
    所有门店共享形象，跨账号不可见。**不要**退化成"任何登录用户可编辑
    任何形象"。鉴权时校验 org_id == 当前用户 id。
    """

    __tablename__ = "live_avatars"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_type: Mapped[str] = mapped_column(
        Enum("image", "video", name="live_avatar_type"),
        nullable=False,
        server_default="image",
    )
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    persona: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "ready", "disabled", name="live_avatar_status"),
        nullable=False,
        server_default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
