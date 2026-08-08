"""add subscription notified note count

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-08-07 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "subscriptions",
        sa.Column("notified_note_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subscriptions", "notified_note_count")
