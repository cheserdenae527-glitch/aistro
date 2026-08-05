"""商圈 POI 记录模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DistrictPoi(Base):
    __tablename__ = "district_pois"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "poi_id", name="uq_district_poi_snapshot_poi"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("district_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    poi_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    typecode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    business_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lng: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_competitor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    is_competitor_auto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    is_competitor_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    excluded_as_self: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
