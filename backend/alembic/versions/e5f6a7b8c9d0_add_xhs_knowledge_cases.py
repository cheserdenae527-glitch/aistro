"""add_xhs_knowledge_cases

Revision ID: e5f6a7b8c9d0
Revises: f9e8d7c6b5a4
Create Date: 2026-08-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add XHS knowledge base cases table."""
    op.create_table(
        "xhs_knowledge_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("style_id", sa.String(length=50), nullable=False),
        sa.Column("category_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column(
            "authorization_status",
            sa.Enum(
                "unauthorized",
                "authorized",
                "internal_only",
                name="xhs_knowledge_auth_status",
            ),
            nullable=False,
            server_default="internal_only",
        ),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_xhs_knowledge_cases_style_id", "xhs_knowledge_cases", ["style_id"]
    )


def downgrade() -> None:
    """Drop XHS knowledge base cases table."""
    op.drop_table("xhs_knowledge_cases")
    op.execute("DROP TYPE IF EXISTS xhs_knowledge_auth_status")