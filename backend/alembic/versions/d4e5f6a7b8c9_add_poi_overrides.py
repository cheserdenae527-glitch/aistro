"""add poi override table and competitor auto/manual flags

Revision ID: d4e5f6a7b8c9
Revises: a9b8c7d6e5f4
Create Date: 2026-08-05 10:00:00.000000

人工标记（竞品/非竞品覆盖）：
- district_poi_overrides 新表（shop_id + poi_id 唯一，跨快照生效）
- district_pois 新增 is_competitor_auto / is_competitor_manual
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "district_pois",
        sa.Column("is_competitor_auto", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "district_pois",
        sa.Column("is_competitor_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # 存量行原本都是自动判定
    op.execute("UPDATE district_pois SET is_competitor_auto = is_competitor")

    op.create_table(
        "district_poi_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("poi_id", sa.String(length=50), nullable=False),
        sa.Column("poi_name", sa.String(length=200), nullable=True),
        sa.Column("is_competitor", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", "poi_id", name="uq_district_poi_override_shop_poi"),
    )
    op.create_index(
        "ix_district_poi_overrides_shop_id",
        "district_poi_overrides",
        ["shop_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_district_poi_overrides_shop_id", table_name="district_poi_overrides")
    op.drop_table("district_poi_overrides")
    op.drop_column("district_pois", "is_competitor_manual")
    op.drop_column("district_pois", "is_competitor_auto")
