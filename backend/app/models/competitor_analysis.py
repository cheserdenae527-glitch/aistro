"""竞对分析模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompetitorAnalysis(Base):
    __tablename__ = "competitor_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    competitor_shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_shops.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_level: Mapped[str | None] = mapped_column(
        Enum("lower", "similar", "higher", name="competitor_price_level", create_type=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
