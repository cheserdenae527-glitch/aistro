"""直播工坊开播场次模型（状态机 + 值守/AI 标识确认）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveSession(Base):
    __tablename__ = "live_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 被引用脚本/形象在删除时受保护（RESTRICT → 409）。
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_scripts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    avatar_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_avatars.id", ondelete="RESTRICT"),
        nullable=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("planned", "live", "ended", "cancelled", name="live_session_status"),
        nullable=False,
        server_default="planned",
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    duty_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    ai_label_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    is_backfilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
