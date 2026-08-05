"""团购工坊方案平台文案模型（一个方案可对应多个平台）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DealSchemeCopy(Base):
    __tablename__ = "deal_scheme_copies"
    __table_args__ = (
        UniqueConstraint("scheme_id", "platform", name="uq_deal_scheme_copy_scheme_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        Enum("douyin", "meituan", "xiaohongshu", name="deal_scheme_copy_platform"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    selling_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
