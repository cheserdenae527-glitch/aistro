"""平台账号装修 Profile 模型 — 乐观锁 version 字段。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShopProfile(Base):
    __tablename__ = "shop_profiles"
    __table_args__ = (
        UniqueConstraint("shop_id", "platform", name="uq_shop_profile_shop_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(
        sa.Enum("xiaohongshu", name="profile_platform", create_type=True),
        nullable=False,
    )

    # ---- 装修内容 ----
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_gen_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_gallery: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    bg_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bg_original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bg_gen_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    bg_gallery: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ---- 色系 ----
    color_primary: Mapped[str | None] = mapped_column(String(7), nullable=True)
    color_secondary: Mapped[str | None] = mapped_column(String(7), nullable=True)
    color_accent: Mapped[str | None] = mapped_column(String(7), nullable=True)
    color_text: Mapped[str | None] = mapped_column(String(7), nullable=True)
    color_mode: Mapped[str | None] = mapped_column(
        sa.Enum("preset", "custom", name="color_mode_enum", create_type=True),
        nullable=True,
    )
    color_preset_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ---- AI 输入历史 ----
    ai_input_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_input_style: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_input_price: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_variants: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    health_check: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ---- 标记与状态 ----
    bio_flagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    status: Mapped[str] = mapped_column(
        sa.Enum("draft", "published", name="profile_status", create_type=True),
        nullable=False,
        server_default="draft",
    )

    # ---- 乐观锁 ----
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # ---- 时间戳 ----
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), 
    )

