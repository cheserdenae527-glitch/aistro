"""blogger_analysis_tasks add with_comments

Revision ID: 8a89baa95354
Revises: e4f5a6b7c8d9
Create Date: 2026-08-11 18:46:45.027001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a89baa95354"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "blogger_analysis_tasks",
        sa.Column("with_comments", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("blogger_analysis_tasks", "with_comments")
