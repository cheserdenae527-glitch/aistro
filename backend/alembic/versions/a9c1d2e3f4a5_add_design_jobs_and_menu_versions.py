"""add design jobs and menu versions

Revision ID: a9c1d2e3f4a5
Revises: f6d0a1b2c3d4
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "f6d0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "design_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("design_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "success", "failed", name="design_job_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_design_jobs_project_id", "design_jobs", ["project_id"])
    op.create_index("ix_design_jobs_user_id", "design_jobs", ["user_id"])
    op.create_index("ix_design_jobs_status", "design_jobs", ["status"])

    op.create_table(
        "menu_design_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "menu_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_designs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_menu_design_versions_menu_id", "menu_design_versions", ["menu_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_menu_design_versions_menu_id", table_name="menu_design_versions")
    op.drop_table("menu_design_versions")
    op.drop_index("ix_design_jobs_status", table_name="design_jobs")
    op.drop_index("ix_design_jobs_user_id", table_name="design_jobs")
    op.drop_index("ix_design_jobs_project_id", table_name="design_jobs")
    op.drop_table("design_jobs")
    op.execute("DROP TYPE IF EXISTS design_job_status")