"""小红书设计知识库案例模型（第二阶段案例库预留）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class XhsKnowledgeCase(Base):
    __tablename__ = "xhs_knowledge_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    style_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    authorization_status: Mapped[str] = mapped_column(
        Enum(
            "unauthorized",
            "authorized",
            "internal_only",
            name="xhs_knowledge_auth_status",
        ),
        nullable=False,
        server_default="internal_only",
    )
    embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )