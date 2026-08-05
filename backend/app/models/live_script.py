"""直播工坊直播脚本模型（批次 + 人设快照 + 合规快照）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveScript(Base):
    __tablename__ = "live_scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 生成时引用的人设来源；被引用时禁止删除形象（409）。
    avatar_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_avatars.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # 生成脚本那一刻从 live_avatars.persona 拷贝的快照；合规/confirm/export 一律用快照。
    persona_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_batch: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    tone: Mapped[str] = mapped_column(String(50), nullable=True)
    content: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    total_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "edited", "confirmed", name="live_script_status"),
        nullable=False,
        server_default="draft",
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    compliance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
