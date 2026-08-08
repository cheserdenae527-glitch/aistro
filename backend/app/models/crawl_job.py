"""爬虫任务模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(
        Enum(
            "meituan", "dianping", "douyin", "xiaohongshu", "eleme",
            name="platform_name", create_type=True,
        ),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(
        Enum(
            "full", "incremental", "search", "note_detail", "comment",
            name="crawl_job_type", create_type=True,
        ),
        nullable=False,
        server_default="full",
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "running", "success", "failed", "cancelled",
            name="crawl_job_status", create_type=True,
        ),
        nullable=False,
        server_default="pending",
    )
    schedule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
