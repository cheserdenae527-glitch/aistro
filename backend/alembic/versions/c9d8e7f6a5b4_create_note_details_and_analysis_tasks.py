"""create note details cache and blogger analysis tasks

Revision ID: c9d8e7f6a5b4
Revises: b1c2d3e4f5a6
Create Date: 2026-08-07 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "note_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("xhs_user_id", sa.String(100), nullable=False),
        sa.Column("platform_note_id", sa.String(100), nullable=False),
        sa.Column("detail_json", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("xhs_user_id", "platform_note_id", name="uq_note_detail_user_note"),
    )
    op.create_index("ix_note_details_xhs_user_id", "note_details", ["xhs_user_id"])

    op.create_table(
        "blogger_analysis_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("xhs_user_id", sa.String(100), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "success", "partial", "failed", "cancelled", name="analysis_task_status", create_type=True), nullable=False, server_default="pending"),
        sa.Column("prescreen_passed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("prescreen_reason", sa.Text(), nullable=True),
        sa.Column("follower_count", sa.Integer(), server_default="0"),
        sa.Column("total_notes", sa.Integer(), server_default="0"),
        sa.Column("target_notes", sa.Integer(), server_default="0"),
        sa.Column("fetched_notes", sa.Integer(), server_default="0"),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_blogger_analysis_tasks_user_id", "blogger_analysis_tasks", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_blogger_analysis_tasks_user_id", table_name="blogger_analysis_tasks")
    op.drop_table("blogger_analysis_tasks")
    op.execute("DROP TYPE IF EXISTS analysis_task_status")
    op.drop_index("ix_note_details_xhs_user_id", table_name="note_details")
    op.drop_table("note_details")
