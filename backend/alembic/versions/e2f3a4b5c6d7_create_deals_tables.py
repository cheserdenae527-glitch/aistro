"""create deals (团购工坊) tables

Revision ID: e2f3a4b5c6d7
Revises: d4e5f6a7b8c9
Create Date: 2026-08-05 12:00:00.000000

团购工坊模块 G1：
- deal_projects / deal_items / competitor_deals / deal_schemes / deal_scheme_copies
- 删除项目 → items/competitor_deals/schemes/copies 全级联
- deal_scheme_copies 唯一约束 (scheme_id, platform)
- design_asset_source 枚举新增 'deals'（导出到视觉设计）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 导出到视觉设计需要 source=deals（沿用 studio 的 ADD VALUE 模式）
    op.execute("ALTER TYPE design_asset_source ADD VALUE IF NOT EXISTS 'deals'")

    op.create_table(
        "deal_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("douyin", "meituan", "xiaohongshu", name="deal_project_platform"),
            nullable=False,
            server_default="douyin",
        ),
        sa.Column("price_band", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "generated", name="deal_project_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_deal_projects_shop_id", "deal_projects", ["shop_id"])

    op.create_table(
        "deal_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deal_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "category",
            sa.Enum("signature", "staple", "snack", "drink", name="deal_item_category"),
            nullable=False,
            server_default="staple",
        ),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_signature", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_high_margin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_deal_items_project_id", "deal_items", ["project_id"])

    op.create_table(
        "competitor_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deal_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("items_summary", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_deals_project_id", "competitor_deals", ["project_id"])

    op.create_table(
        "deal_schemes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deal_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scheme_type",
            sa.Enum("hook", "profit", "scenario", name="deal_scheme_type"),
            nullable=False,
        ),
        sa.Column("generation_batch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("items", postgresql.JSONB(), nullable=True),
        sa.Column("original_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("deal_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("cost_estimate", sa.Numeric(10, 2), nullable=True),
        sa.Column("margin_estimate", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "edited", "generated", name="deal_scheme_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_deal_schemes_project_id", "deal_schemes", ["project_id"])

    op.create_table(
        "deal_scheme_copies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scheme_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deal_schemes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.Enum("douyin", "meituan", "xiaohongshu", name="deal_scheme_copy_platform"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("selling_points", postgresql.JSONB(), nullable=True),
        sa.Column("rules", sa.Text(), nullable=True),
        sa.Column("cover_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "scheme_id", "platform", name="uq_deal_scheme_copy_scheme_platform"
        ),
    )
    op.create_index("ix_deal_scheme_copies_scheme_id", "deal_scheme_copies", ["scheme_id"])


def downgrade() -> None:
    op.drop_index("ix_deal_scheme_copies_scheme_id", table_name="deal_scheme_copies")
    op.drop_table("deal_scheme_copies")
    op.drop_index("ix_deal_schemes_project_id", table_name="deal_schemes")
    op.drop_table("deal_schemes")
    op.drop_index("ix_competitor_deals_project_id", table_name="competitor_deals")
    op.drop_table("competitor_deals")
    op.drop_index("ix_deal_items_project_id", table_name="deal_items")
    op.drop_table("deal_items")
    op.drop_index("ix_deal_projects_shop_id", table_name="deal_projects")
    op.drop_table("deal_projects")
    op.execute("DROP TYPE IF EXISTS deal_scheme_copy_platform")
    op.execute("DROP TYPE IF EXISTS deal_scheme_status")
    op.execute("DROP TYPE IF EXISTS deal_scheme_type")
    op.execute("DROP TYPE IF EXISTS deal_item_category")
    op.execute("DROP TYPE IF EXISTS deal_project_status")
    op.execute("DROP TYPE IF EXISTS deal_project_platform")
    # design_asset_source 的 'deals' 值不做回退（PG 枚举值无法安全移除，且为存量表共用类型）
