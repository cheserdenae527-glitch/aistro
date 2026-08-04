"""商圈快照模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DistrictSnapshot(Base):
    __tablename__ = "district_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    center_lng: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    center_lat: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    geocode_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3000")
    poi_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    competitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    category_stats: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    density_per_km2: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    mapping_status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="none",
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="analyzed",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )

