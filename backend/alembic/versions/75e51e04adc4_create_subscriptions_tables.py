"""create subscriptions tables

Revision ID: 75e51e04adc4
Revises: 0ee697938e51
Create Date: 2026-07-31 14:26:31.848442

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '75e51e04adc4'
down_revision: Union[str, Sequence[str], None] = '0ee697938e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('xhs_user_id', sa.String(100), nullable=False),
        sa.Column('nickname', sa.String(100), nullable=False),
        sa.Column('avatar', sa.Text(), nullable=True),
        sa.Column('note_count', sa.Integer(), server_default='0'),
        sa.Column('follower_count', sa.Integer(), server_default='0'),
        sa.Column('following_count', sa.Integer(), server_default='0'),
        sa.Column('last_crawled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'subscription_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('note_count', sa.Integer(), server_default='0'),
        sa.Column('follower_count', sa.Integer(), server_default='0'),
        sa.Column('following_count', sa.Integer(), server_default='0'),
        sa.Column('crawled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('subscription_snapshots')
    op.drop_table('subscriptions')
