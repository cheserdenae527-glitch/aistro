"""add_profile_image_galleries

Revision ID: d2f3a9c1b4e6
Revises: c68d050a09c4
Create Date: 2026-08-03 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd2f3a9c1b4e6'
down_revision: Union[str, Sequence[str], None] = 'c68d050a09c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add generated image gallery columns."""
    op.add_column(
        'shop_profiles',
        sa.Column(
            'avatar_gallery',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        'shop_profiles',
        sa.Column(
            'bg_gallery',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop generated image gallery columns."""
    op.drop_column('shop_profiles', 'bg_gallery')
    op.drop_column('shop_profiles', 'avatar_gallery')
