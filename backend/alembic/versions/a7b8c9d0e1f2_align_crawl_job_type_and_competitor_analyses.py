"""align crawl job type and create competitor analyses

Revision ID: a7b8c9d0e1f2
Revises: d3e4f5a6b7c8
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # crawl_jobs.job_type 对齐 M5 实际任务类型（保留历史 full/incremental 兼容）
    op.execute("ALTER TYPE crawl_job_type ADD VALUE 'search'")
    op.execute("ALTER TYPE crawl_job_type ADD VALUE 'note_detail'")
    op.execute("ALTER TYPE crawl_job_type ADD VALUE 'comment'")

    op.create_table(
        "competitor_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_report", postgresql.JSONB(), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("price_level", sa.Enum("lower", "similar", "higher", name="competitor_price_level", create_type=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("competitor_analyses")
    op.execute("DROP TYPE IF EXISTS competitor_price_level")

    # 回退枚举到历史定义（新枚举值存在时该转换会失败，属于预期保护）
    op.execute("ALTER TYPE crawl_job_type RENAME TO crawl_job_type_old")
    op.execute("CREATE TYPE crawl_job_type AS ENUM ('full', 'incremental')")
    op.execute(
        "ALTER TABLE crawl_jobs ALTER COLUMN job_type TYPE crawl_job_type "
        "USING job_type::text::crawl_job_type"
    )
    op.execute("DROP TYPE crawl_job_type_old")
