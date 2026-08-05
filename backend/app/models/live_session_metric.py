"""直播工坊场次复盘数据模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveSessionMetric(Base):
    __tablename__ = "live_session_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(
        Enum("manual", "import", name="live_metrics_source"),
        nullable=False,
        server_default="manual",
    )
    ai_review: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
