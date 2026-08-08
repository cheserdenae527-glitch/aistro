"""爬虫请求结果观测表（风控校准数据，方案 §1.4 / 附录 A）。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrawlRequestLog(Base):
    __tablename__ = "crawl_request_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="redcrack")
    job_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    target: Mapped[str] = mapped_column(sa.String(255), nullable=False, server_default="")
    result: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    risk_type: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    http_status: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    interval_before_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    proxy_used: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    record_key: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )

    __table_args__ = (
        sa.Index("ix_crawl_request_log_result_created", "result", "created_at"),
    )
