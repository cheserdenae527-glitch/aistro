"""直播工坊项目模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveProject(Base):
    __tablename__ = "live_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(
        Enum("douyin", "xiaohongshu", "wechat", name="live_project_platform"),
        nullable=False,
        server_default="douyin",
    )
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_label_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    engine_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "active", "archived", name="live_project_status"),
        nullable=False,
        server_default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
