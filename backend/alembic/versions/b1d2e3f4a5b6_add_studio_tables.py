"""add studio tables

Revision ID: b1d2e3f4a5b6
Revises: a9c1d2e3f4a5
Create Date: 2026-08-04 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a9c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 导出到视觉设计需要 source=studio
    op.execute("ALTER TYPE design_asset_source ADD VALUE IF NOT EXISTS 'studio'")

    op.create_table(
        "studio_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "generated", name="studio_project_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_projects_shop_id", "studio_projects", ["shop_id"])

    op.create_table(
        "studio_copies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studio_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("titles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("image_guide", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_copies_project_id", "studio_copies", ["project_id"])

    op.create_table(
        "studio_decks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studio_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "copy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studio_copies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template",
            sa.Enum("editorial", "swiss", name="studio_deck_template"),
            nullable=False,
        ),
        sa.Column("theme", sa.String(length=50), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("page_specs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_assets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("images", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qa_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "rendered", "failed", name="studio_deck_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_decks_project_id", "studio_decks", ["project_id"])
    op.create_index("ix_studio_decks_copy_id", "studio_decks", ["copy_id"])


def downgrade() -> None:
    op.drop_index("ix_studio_decks_copy_id", table_name="studio_decks")
    op.drop_index("ix_studio_decks_project_id", table_name="studio_decks")
    op.drop_table("studio_decks")
    op.drop_index("ix_studio_copies_project_id", table_name="studio_copies")
    op.drop_table("studio_copies")
    op.drop_index("ix_studio_projects_shop_id", table_name="studio_projects")
    op.drop_table("studio_projects")
    op.execute("ALTER TYPE design_asset_source DROP VALUE IF EXISTS 'studio'")
