"""评价模型。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index(
            "uq_reviews_platform_shop_type_review_id",
            "platform_shop_id",
            "review_type",
            "platform_review_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False
    )
    platform_review_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(
        Enum("positive", "neutral", "negative", name="review_sentiment", create_type=True),
        nullable=True,
    )
    reply_status: Mapped[str | None] = mapped_column(
        Enum(
            "unreplied", "ai_replied", "manual_replied",
            name="review_reply_status", create_type=True,
        ),
        nullable=True,
    )
    ai_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_type: Mapped[str] = mapped_column(
        Enum(
            "note", "comment", "rating_review",
            name="review_type", create_type=True,
        ),
        nullable=False,
        server_default="rating_review",
    )
    parent_review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    note_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    interact_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    alert_status: Mapped[str] = mapped_column(
        Enum(
            "none", "triggered", "acknowledged",
            name="review_alert_status", create_type=True,
        ),
        nullable=False,
        server_default="none",
    )
    alert_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
