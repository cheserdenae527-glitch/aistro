"""订阅博主模型。"""
from __future__ import annotations
import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False)
    xhs_user_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    nickname: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    avatar: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    note_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    follower_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    following_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    notified_note_count: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    last_crawled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_deep_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

class SubscriptionSnapshot(Base):
    __tablename__ = 'subscription_snapshots'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('subscriptions.id', ondelete='CASCADE'), nullable=False)
    note_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    follower_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    following_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    crawled_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
