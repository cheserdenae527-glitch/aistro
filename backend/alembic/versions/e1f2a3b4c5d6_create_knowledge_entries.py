"""create knowledge entries for crawler knowledge base

Revision ID: e1f2a3b4c5d6
Revises: e5f6a7b8c9d0
Create Date: 2026-08-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "knowledge_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="xhs"),
        sa.Column("platform_note_id", sa.String(100), nullable=False),
        sa.Column("xhs_user_id", sa.String(100), nullable=True),
        sa.Column("author_nickname", sa.String(100), nullable=False, server_default=""),
        sa.Column("author_avatar", sa.Text(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("desc", sa.Text(), nullable=True),
        sa.Column("note_type", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("image_urls", postgresql.JSONB(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("stats", postgresql.JSONB(), nullable=True),
        sa.Column("liked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shared_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("note_url", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform_note_id", name="uq_knowledge_user_note"),
    )
    op.create_index("ix_knowledge_entries_user_id", "knowledge_entries", ["user_id"])
    op.create_index("ix_knowledge_entries_platform_note_id", "knowledge_entries", ["platform_note_id"])
    op.create_index("ix_knowledge_entries_xhs_user_id", "knowledge_entries", ["xhs_user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_knowledge_entries_xhs_user_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_platform_note_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_user_id", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
