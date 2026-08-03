"""create design module tables

Revision ID: e5f0d1a2b3c4
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5f0d1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "design_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="design_project_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_design_projects_shop_id", "design_projects", ["shop_id"]
    )

    op.create_table(
        "design_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("design_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_type",
            sa.Enum("dish", "logo", "photo", name="design_asset_type"),
            nullable=False,
            server_default="photo",
        ),
        sa.Column(
            "source",
            sa.Enum("upload", "ai", name="design_asset_source"),
            nullable=False,
            server_default="upload",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "discarded", name="design_asset_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "derived_from_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("design_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("processed_url", sa.Text(), nullable=True),
        sa.Column("thumb_url", sa.Text(), nullable=True),
        sa.Column("edit_stack", postgresql.JSONB(), nullable=True),
        sa.Column("beauty_config", postgresql.JSONB(), nullable=True),
        sa.Column("dish_name", sa.String(200), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("tagline", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_design_assets_project_id", "design_assets", ["project_id"]
    )
    op.create_index(
        "ix_design_assets_status", "design_assets", ["status"]
    )
    op.create_index(
        "ix_design_assets_batch_id", "design_assets", ["batch_id"]
    )
    op.create_index(
        "ix_design_assets_derived_from_asset_id",
        "design_assets",
        ["derived_from_asset_id"],
    )

    op.create_table(
        "menu_designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("design_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "menu_type",
            sa.Enum("xhs", "a4", name="menu_type"),
            nullable=False,
            server_default="xhs",
        ),
        sa.Column("template_id", sa.String(50), nullable=False),
        sa.Column("shop_name", sa.String(100), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("color_scheme", postgresql.JSONB(), nullable=True),
        sa.Column("items", postgresql.JSONB(), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "rendered", name="menu_design_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_menu_designs_project_id", "menu_designs", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_menu_designs_project_id", table_name="menu_designs")
    op.drop_table("menu_designs")
    op.drop_index("ix_design_assets_derived_from_asset_id", table_name="design_assets")
    op.drop_index("ix_design_assets_batch_id", table_name="design_assets")
    op.drop_index("ix_design_assets_status", table_name="design_assets")
    op.drop_index("ix_design_assets_project_id", table_name="design_assets")
    op.drop_table("design_assets")
    op.drop_index("ix_design_projects_shop_id", table_name="design_projects")
    op.drop_table("design_projects")
    op.execute("DROP TYPE IF EXISTS menu_design_status")
    op.execute("DROP TYPE IF EXISTS menu_type")
    op.execute("DROP TYPE IF EXISTS design_asset_status")
    op.execute("DROP TYPE IF EXISTS design_asset_source")
    op.execute("DROP TYPE IF EXISTS design_asset_type")
    op.execute("DROP TYPE IF EXISTS design_project_status")
