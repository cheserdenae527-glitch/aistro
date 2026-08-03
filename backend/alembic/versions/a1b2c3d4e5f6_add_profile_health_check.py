"""add_profile_health_check

Revision ID: a1b2c3d4e5f6
Revises: d2f3a9c1b4e6
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd2f3a9c1b4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add homepage health check result column."""
    op.add_column(
        'shop_profiles',
        sa.Column(
            'health_check',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop homepage health check result column."""
    op.drop_column('shop_profiles', 'health_check')
