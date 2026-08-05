"""create live (直播工坊) tables

Revision ID: f0a1b2c3d4e5
Revises: e2f3a4b5c6d7
Create Date: 2026-08-05 12:30:00.000000

直播工坊模块 L1（SPEC-LIVESTREAM v0.6 / PLAN-LIVESTREAM L1）：
- live_projects / live_avatars / live_scripts / live_danmaku_configs
  / live_sessions / live_session_metrics
- 级联：删除 live_projects → scripts / danmaku_configs / sessions
  （→ metrics）全级联
- live_avatars.org_id：系统尚无 org/租户模型，MVP 退化映射为创建该形象的
  用户主账号 ID（users.id，见 SPEC §4/§10），效果=同账号门店共享、跨账号不可见
- 删除保护：live_scripts.avatar_id / live_sessions.avatar_id 用 RESTRICT，
  被引用时删除形象返回 409；live_sessions.script_id 用 RESTRICT（被引用脚本不可删）
- live_danmaku_configs.project_id 唯一（一项目一条），source_script_id 用 SET NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "live_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("douyin", "xiaohongshu", "wechat", name="live_project_platform"),
            nullable=False,
            server_default="douyin",
        ),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("promo_items", postgresql.JSONB(), nullable=True),
        sa.Column("ai_label_text", sa.String(length=200), nullable=True),
        sa.Column("engine_config", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="live_project_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_live_projects_shop_id", "live_projects", ["shop_id"])

    op.create_table(
        "live_avatars",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "avatar_type",
            sa.Enum("image", "video", name="live_avatar_type"),
            nullable=False,
            server_default="image",
        ),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("voice_config", postgresql.JSONB(), nullable=True),
        sa.Column("persona", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "ready", "disabled", name="live_avatar_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_live_avatars_org_id", "live_avatars", ["org_id"])

    op.create_table(
        "live_scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_avatars.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("persona_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("generation_batch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("tone", sa.String(length=50), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=True),
        sa.Column("total_duration_sec", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "edited", "confirmed", name="live_script_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("compliance", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_live_scripts_project_id", "live_scripts", ["project_id"])

    op.create_table(
        "live_danmaku_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("persona", postgresql.JSONB(), nullable=True),
        sa.Column("reply_rules", postgresql.JSONB(), nullable=True),
        sa.Column("sensitive_words", postgresql.JSONB(), nullable=True),
        sa.Column("escalate_topics", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_live_danmaku_configs_project_id", "live_danmaku_configs", ["project_id"]
    )

    op.create_table(
        "live_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_scripts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_avatars.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("planned", "live", "ended", "cancelled", name="live_session_status"),
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("duty_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_label_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_backfilled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_live_sessions_project_id", "live_sessions", ["project_id"])

    op.create_table(
        "live_session_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("manual", "import", name="live_metrics_source"),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("ai_review", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_live_session_metrics_session_id", "live_session_metrics", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_live_session_metrics_session_id", table_name="live_session_metrics")
    op.drop_table("live_session_metrics")
    op.drop_index("ix_live_sessions_project_id", table_name="live_sessions")
    op.drop_table("live_sessions")
    op.drop_index("ix_live_danmaku_configs_project_id", table_name="live_danmaku_configs")
    op.drop_table("live_danmaku_configs")
    op.drop_index("ix_live_scripts_project_id", table_name="live_scripts")
    op.drop_table("live_scripts")
    op.drop_index("ix_live_avatars_org_id", table_name="live_avatars")
    op.drop_table("live_avatars")
    op.drop_index("ix_live_projects_shop_id", table_name="live_projects")
    op.drop_table("live_projects")
    op.execute("DROP TYPE IF EXISTS live_metrics_source")
    op.execute("DROP TYPE IF EXISTS live_session_status")
    op.execute("DROP TYPE IF EXISTS live_script_status")
    op.execute("DROP TYPE IF EXISTS live_avatar_status")
    op.execute("DROP TYPE IF EXISTS live_avatar_type")
    op.execute("DROP TYPE IF EXISTS live_project_status")
    op.execute("DROP TYPE IF EXISTS live_project_platform")
