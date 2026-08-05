"""add amap detail fields to district_pois

Revision ID: a9b8c7d6e5f4
Revises: c3d4e5f6a7b8
Create Date: 2026-08-04 18:00:00.000000

竞品深度数据（高德 place/around extensions=all + place/detail）：
typecode / tel / tag / business_area / rating / cost / business_hours
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("district_pois", sa.Column("typecode", sa.String(length=50), nullable=True))
    op.add_column("district_pois", sa.Column("tel", sa.String(length=40), nullable=True))
    op.add_column("district_pois", sa.Column("tag", sa.String(length=255), nullable=True))
    op.add_column("district_pois", sa.Column("business_area", sa.String(length=100), nullable=True))
    op.add_column("district_pois", sa.Column("rating", sa.Numeric(3, 1), nullable=True))
    op.add_column("district_pois", sa.Column("cost", sa.Numeric(8, 2), nullable=True))
    op.add_column("district_pois", sa.Column("business_hours", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("district_pois", "business_hours")
    op.drop_column("district_pois", "cost")
    op.drop_column("district_pois", "rating")
    op.drop_column("district_pois", "business_area")
    op.drop_column("district_pois", "tag")
    op.drop_column("district_pois", "tel")
    op.drop_column("district_pois", "typecode")
