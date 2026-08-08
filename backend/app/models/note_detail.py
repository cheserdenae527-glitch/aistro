"""笔记详情快照缓存模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NoteDetail(Base):
    __tablename__ = "note_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    xhs_user_id: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    platform_note_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    detail_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("xhs_user_id", "platform_note_id", name="uq_note_detail_user_note"),
    )
