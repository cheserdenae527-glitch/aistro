"""create core tables

Revision ID: 0ee697938e51
Revises: 09ee12f576bb
Create Date: 2026-07-30 15:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0ee697938e51"
down_revision: Union[str, Sequence[str], None] = "09ee12f576bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### merchants ###
    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("tier", sa.Enum("trial", "pro", "enterprise", name="merchant_tier", create_type=True), nullable=False, server_default="trial"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### shops ###
    op.create_table(
        "shops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### platform_shops ###
    op.create_table(
        "platform_shops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.Enum("meituan", "dianping", "douyin", "xiaohongshu", "eleme", name="platform_name", create_type=True), nullable=False),
        sa.Column("platform_shop_id", sa.String(100), nullable=True),
        sa.Column("shop_url", sa.Text(), nullable=True),
        sa.Column("shop_name", sa.String(200), nullable=True),
        sa.Column("rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("monthly_sales", sa.Integer(), nullable=True),
        sa.Column("total_reviews", sa.Integer(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### reviews ###
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_review_id", sa.String(100), nullable=True),
        sa.Column("reviewer_name", sa.String(100), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("sentiment", sa.Enum("positive", "neutral", "negative", name="review_sentiment", create_type=True), nullable=True),
        sa.Column("reply_status", sa.Enum("unreplied", "ai_replied", "manual_replied", name="review_reply_status", create_type=True), nullable=False, server_default="unreplied"),
        sa.Column("ai_reply", sa.Text(), nullable=True),
        sa.Column("reply_content", sa.Text(), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### menu_items ###
    op.create_table(
        "menu_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("original_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("sales_count", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("ai_optimized_name", sa.Text(), nullable=True),
        sa.Column("ai_optimized_desc", sa.Text(), nullable=True),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### crawl_jobs ###
    op.create_table(
        "crawl_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.Enum("meituan", "dianping", "douyin", "xiaohongshu", "eleme", name="platform_name", create_type=True), nullable=False),
        sa.Column("job_type", sa.Enum("full", "incremental", name="crawl_job_type", create_type=True), nullable=False, server_default="full"),
        sa.Column("status", sa.Enum("pending", "running", "success", "failed", "cancelled", name="crawl_job_status", create_type=True), nullable=False, server_default="pending"),
        sa.Column("schedule", sa.String(50), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### reports ###
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.Enum("weekly", "daily", "competitor", name="report_type", create_type=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Enum("draft", "published", name="report_status", create_type=True), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ### manual_imports ###
    op.create_table(
        "manual_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("import_type", sa.Enum("reviews_csv", "reviews_paste", "menu_csv", "shop_data", name="import_type", create_type=True), nullable=False),
        sa.Column("source_data", sa.Text(), nullable=True),
        sa.Column("parsed_result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Enum("pending", "parsed", "imported", "failed", name="import_status", create_type=True), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("manual_imports")
    op.drop_table("reports")
    op.drop_table("crawl_jobs")
    op.drop_table("menu_items")
    op.drop_table("reviews")
    op.drop_table("platform_shops")
    op.drop_table("shops")
    op.drop_table("merchants")
    op.execute("DROP TYPE IF EXISTS import_status")
    op.execute("DROP TYPE IF EXISTS import_type")
    op.execute("DROP TYPE IF EXISTS report_status")
    op.execute("DROP TYPE IF EXISTS report_type")
    op.execute("DROP TYPE IF EXISTS crawl_job_status")
    op.execute("DROP TYPE IF EXISTS crawl_job_type")
    op.execute("DROP TYPE IF EXISTS review_reply_status")
    op.execute("DROP TYPE IF EXISTS review_sentiment")
    op.execute("DROP TYPE IF EXISTS platform_name")
    op.execute("DROP TYPE IF EXISTS merchant_tier")
