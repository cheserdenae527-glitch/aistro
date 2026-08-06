"""add_profile_pinned_notes

Revision ID: c2d3e4f5a6b7
Revises: a1d2e3f4a5b6
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pinned notes column."""
    op.add_column(
        "shop_profiles",
        sa.Column(
            "pinned_notes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop pinned notes column."""
    op.drop_column("shop_profiles", "pinned_notes")
