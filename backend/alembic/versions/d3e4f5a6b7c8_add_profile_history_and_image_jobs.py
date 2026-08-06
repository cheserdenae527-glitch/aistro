"""add_profile_history_and_image_jobs

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-06 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add profile history and background image job tables."""
    op.create_table(
        "shop_profile_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_shop_profile_history_profile_id",
        "shop_profile_history",
        ["profile_id"],
    )

    op.create_table(
        "profile_image_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=10), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                name="profile_image_job_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_profile_image_jobs_shop_id", "profile_image_jobs", ["shop_id"])
    op.create_index("ix_profile_image_jobs_user_id", "profile_image_jobs", ["user_id"])
    op.create_index("ix_profile_image_jobs_status", "profile_image_jobs", ["status"])


def downgrade() -> None:
    """Drop profile history and image job tables."""
    op.drop_table("profile_image_jobs")
    op.drop_table("shop_profile_history")
