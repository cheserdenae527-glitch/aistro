"""add reputation review fields

Revision ID: f8d4a2c6e0f1
Revises: e5f0d1a2b3c4
Create Date: 2026-08-03 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f8d4a2c6e0f1"
down_revision: Union[str, Sequence[str], None] = "e5f0d1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REVIEW_TYPE = sa.Enum("note", "comment", "rating_review", name="review_type")
_ALERT_STATUS = sa.Enum("none", "triggered", "acknowledged", name="review_alert_status")
_REPLY_STATUS = sa.Enum(
    "unreplied", "ai_replied", "manual_replied", name="review_reply_status"
)


def upgrade() -> None:
    op.execute("CREATE TYPE review_type AS ENUM ('note', 'comment', 'rating_review')")
    op.execute("CREATE TYPE review_alert_status AS ENUM ('none', 'triggered', 'acknowledged')")

    # 数据体检：同一平台店铺内 platform_review_id 重复的历史记录，保留最早一条。
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY platform_shop_id, platform_review_id
                       ORDER BY created_at, id
                   ) AS rn
            FROM reviews
            WHERE platform_review_id IS NOT NULL
        )
        DELETE FROM reviews r
        USING ranked
        WHERE r.id = ranked.id AND ranked.rn > 1
        """
    )

    op.add_column(
        "reviews",
        sa.Column(
            "review_type",
            sa.Enum(
                "note",
                "comment",
                "rating_review",
                name="review_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "reviews",
        sa.Column("parent_review_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_reviews_parent_review_id",
        "reviews",
        "reviews",
        ["parent_review_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("reviews", sa.Column("note_title", sa.String(200), nullable=True))
    op.add_column("reviews", sa.Column("note_url", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("author_id", sa.String(100), nullable=True))
    op.add_column("reviews", sa.Column("author_avatar", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("interact_stats", postgresql.JSONB(), nullable=True))
    op.add_column("reviews", sa.Column("source_json", postgresql.JSONB(), nullable=True))
    op.add_column(
        "reviews",
        sa.Column(
            "alert_status",
            sa.Enum(
                "none",
                "triggered",
                "acknowledged",
                name="review_alert_status",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column("reviews", sa.Column("alert_reason", postgresql.JSONB(), nullable=True))

    # 历史记录统一回填：老平台评价默认 rating_review。
    op.execute("UPDATE reviews SET review_type = 'rating_review' WHERE review_type IS NULL")
    op.alter_column(
        "reviews",
        "review_type",
        existing_type=sa.Enum(
            "note",
            "comment",
            "rating_review",
            name="review_type",
            create_type=False,
        ),
        nullable=False,
        server_default="rating_review",
    )

    op.execute("UPDATE reviews SET alert_status = 'none' WHERE alert_status IS NULL")
    op.alter_column(
        "reviews",
        "alert_status",
        existing_type=sa.Enum(
            "none",
            "triggered",
            "acknowledged",
            name="review_alert_status",
            create_type=False,
        ),
        nullable=False,
        server_default="none",
    )

    # reply_status 改为 nullable：笔记记录不参与回复筛选。
    op.execute("ALTER TABLE reviews ALTER COLUMN reply_status DROP DEFAULT")
    op.alter_column(
        "reviews",
        "reply_status",
        existing_type=_REPLY_STATUS,
        nullable=True,
    )

    op.create_index(
        "uq_reviews_platform_shop_type_review_id",
        "reviews",
        ["platform_shop_id", "review_type", "platform_review_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_reviews_platform_shop_type_review_id", table_name="reviews")

    op.execute("UPDATE reviews SET reply_status = 'unreplied' WHERE reply_status IS NULL")
    op.alter_column(
        "reviews",
        "reply_status",
        existing_type=_REPLY_STATUS,
        nullable=False,
        server_default="unreplied",
    )

    op.drop_constraint("fk_reviews_parent_review_id", "reviews", type_="foreignkey")
    op.drop_column("reviews", "alert_reason")
    op.drop_column("reviews", "alert_status")
    op.drop_column("reviews", "source_json")
    op.drop_column("reviews", "interact_stats")
    op.drop_column("reviews", "author_avatar")
    op.drop_column("reviews", "author_id")
    op.drop_column("reviews", "note_url")
    op.drop_column("reviews", "note_title")
    op.drop_column("reviews", "parent_review_id")
    op.drop_column("reviews", "review_type")
    op.execute("DROP TYPE IF EXISTS review_alert_status")
    op.execute("DROP TYPE IF EXISTS review_type")
