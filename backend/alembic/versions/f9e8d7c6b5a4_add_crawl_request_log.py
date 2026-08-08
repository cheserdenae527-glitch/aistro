"""add crawl_request_log

Revision ID: f9e8d7c6b5a4
Revises: d0e1f2a3b4c5
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "crawl_request_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False, server_default="redcrack"),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("target", sa.String(255), nullable=False, server_default=""),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("risk_type", sa.String(32), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("interval_before_ms", sa.Integer(), nullable=True),
        sa.Column("proxy_used", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("record_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_key", name="uq_crawl_request_log_record_key"),
    )
    op.create_index("ix_crawl_request_log_created_at", "crawl_request_log", ["created_at"])
    op.create_index("ix_crawl_request_log_result_created", "crawl_request_log", ["result", "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_crawl_request_log_result_created", table_name="crawl_request_log")
    op.drop_index("ix_crawl_request_log_created_at", table_name="crawl_request_log")
    op.drop_table("crawl_request_log")
