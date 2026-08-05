"""团购工坊 AI 生成的套餐方案模型。"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DealScheme(Base):
    __tablename__ = "deal_schemes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheme_type: Mapped[str] = mapped_column(
        Enum("hook", "profit", "scenario", name="deal_scheme_type"),
        nullable=False,
    )
    generation_batch: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deal_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    margin_estimate: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "edited", "generated", name="deal_scheme_status"),
        nullable=False,
        server_default="draft",
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
