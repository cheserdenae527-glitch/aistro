"""视觉设计图片素材模型 — 支持 AI 候选生命周期。"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DesignAsset(Base):
    __tablename__ = "design_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[str] = mapped_column(
        Enum("dish", "logo", "photo", name="design_asset_type"),
        nullable=False,
        server_default="photo",
    )
    source: Mapped[str] = mapped_column(
        Enum("upload", "ai", "studio", name="design_asset_source"),
        nullable=False,
        server_default="upload",
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "active", "discarded", name="design_asset_status"),
        nullable=False,
        server_default="pending",
        index=True,
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    derived_from_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("design_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_stack: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    beauty_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    dish_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )

