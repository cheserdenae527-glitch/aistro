"""商圈 POI 人工标记（竞品/非竞品覆盖）模型。

按「门店 + 高德 POI」维度持久，跨快照生效：重新分析时新快照自动沿用人工标记。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DistrictPoiOverride(Base):
    __tablename__ = "district_poi_overrides"
    __table_args__ = (
        UniqueConstraint("shop_id", "poi_id", name="uq_district_poi_override_shop_poi"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
    )
    poi_id: Mapped[str] = mapped_column(String(50), nullable=False)
    poi_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
