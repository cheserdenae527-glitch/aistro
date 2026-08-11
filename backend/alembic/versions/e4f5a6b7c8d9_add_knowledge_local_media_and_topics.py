"""add local media, topics and content markdown to knowledge entries

Revision ID: e4f5a6b7c8d9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("knowledge_entries", sa.Column("topics", postgresql.JSONB(), nullable=True))
    op.add_column("knowledge_entries", sa.Column("content_md", sa.Text(), nullable=True))
    op.add_column("knowledge_entries", sa.Column("cover_local", sa.Text(), nullable=True))
    op.add_column("knowledge_entries", sa.Column("image_urls_local", postgresql.JSONB(), nullable=True))
    op.add_column("knowledge_entries", sa.Column("video_local", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("knowledge_entries", "video_local")
    op.drop_column("knowledge_entries", "image_urls_local")
    op.drop_column("knowledge_entries", "cover_local")
    op.drop_column("knowledge_entries", "content_md")
    op.drop_column("knowledge_entries", "topics")
