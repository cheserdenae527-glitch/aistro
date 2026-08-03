"""add_shop_profiles

Revision ID: c68d050a09c4
Revises: 75e51e04adc4
Create Date: 2026-07-31 16:49:12.842624

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c68d050a09c4'
down_revision: Union[str, Sequence[str], None] = '75e51e04adc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('shop_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('shop_id', sa.UUID(), nullable=False),
    sa.Column('platform', sa.Enum('xiaohongshu', name='profile_platform'), nullable=False),
    sa.Column('nickname', sa.String(length=50), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('avatar_original_url', sa.Text(), nullable=True),
    sa.Column('avatar_gen_prompt', sa.Text(), nullable=True),
    sa.Column('bg_image_url', sa.Text(), nullable=True),
    sa.Column('bg_original_url', sa.Text(), nullable=True),
    sa.Column('bg_gen_prompt', sa.Text(), nullable=True),
    sa.Column('color_primary', sa.String(length=7), nullable=True),
    sa.Column('color_secondary', sa.String(length=7), nullable=True),
    sa.Column('color_accent', sa.String(length=7), nullable=True),
    sa.Column('color_text', sa.String(length=7), nullable=True),
    sa.Column('color_mode', sa.Enum('preset', 'custom', name='color_mode_enum'), nullable=True),
    sa.Column('color_preset_name', sa.String(length=50), nullable=True),
    sa.Column('ai_input_category', sa.String(length=50), nullable=True),
    sa.Column('ai_input_style', sa.String(length=200), nullable=True),
    sa.Column('ai_input_price', sa.String(length=50), nullable=True),
    sa.Column('ai_variants', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('bio_flagged', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.Enum('draft', 'published', name='profile_status'), server_default='draft', nullable=False),
    sa.Column('version', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('shop_id', 'platform', name='uq_shop_profile_shop_platform')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('shop_profiles')
