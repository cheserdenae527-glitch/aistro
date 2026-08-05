"""直播工坊弹幕互动配置模型（一项目一条，不做版本归档）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveDanmakuConfig(Base):
    __tablename__ = "live_danmaku_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # 生成本批弹幕规则时依据的脚本版本；脚本被删则置空（SET NULL）。
    source_script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_scripts.id", ondelete="SET NULL"),
        nullable=True,
    )
    persona: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reply_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sensitive_words: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    escalate_topics: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
