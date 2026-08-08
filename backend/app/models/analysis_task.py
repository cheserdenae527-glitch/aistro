"""博主分析任务模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BloggerAnalysisTask(Base):
    __tablename__ = "blogger_analysis_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    xhs_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "success", "partial", "failed", "cancelled", name="analysis_task_status", create_type=True),
        nullable=False,
        server_default="pending",
    )
    prescreen_passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    prescreen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    follower_count: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    total_notes: Mapped[int] = mapped_column(sa.Integer, default=0)
    target_notes: Mapped[int] = mapped_column(sa.Integer, default=0)
    fetched_notes: Mapped[int] = mapped_column(sa.Integer, default=0)
    coverage: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
