"""create district tables

Revision ID: c3d4e5f6a7b8
Revises: b1d2e3f4a5b6
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "district_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("center_lng", sa.Numeric(10, 6), nullable=True),
        sa.Column("center_lat", sa.Numeric(10, 6), nullable=True),
        sa.Column("geocode_level", sa.String(50), nullable=True),
        sa.Column("radius_m", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("poi_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("competitor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category_stats", postgresql.JSONB(), nullable=True),
        sa.Column("density_per_km2", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "mapping_status",
            sa.String(20),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="analyzed",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "district_pois",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("district_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("poi_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("lng", sa.Numeric(10, 6), nullable=True),
        sa.Column("lat", sa.Numeric(10, 6), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_competitor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("excluded_as_self", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_id", "poi_id", name="uq_district_poi_snapshot_poi"),
    )

    op.create_index(
        "ix_district_snapshots_shop_id", "district_snapshots", ["shop_id"]
    )
    op.create_index(
        "ix_district_pois_snapshot_id", "district_pois", ["snapshot_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_district_pois_snapshot_id", table_name="district_pois")
    op.drop_index("ix_district_snapshots_shop_id", table_name="district_snapshots")
    op.drop_table("district_pois")
    op.drop_table("district_snapshots")

