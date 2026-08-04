"""add menu output pages

Revision ID: f6d0a1b2c3d4
Revises: e5f0d1a2b3c4
Create Date: 2026-08-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6d0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "f8d4a2c6e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "menu_designs",
        sa.Column("output_pages", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("menu_designs", "output_pages")