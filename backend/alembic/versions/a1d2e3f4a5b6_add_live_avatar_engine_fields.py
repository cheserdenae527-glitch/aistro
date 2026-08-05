"""add live_avatars engine sync fields

Revision ID: a1d2e3f4a5b6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-05 14:30:00.000000

直播工坊 L3 增强：数字人形象与本地引擎 Avatar 生成 API 对接。
- live_avatars.engine_base_url：引擎管理后台地址（生成形象用）
- live_avatars.engine_avatar_id：引擎侧生成的形象 ID（data/avatars/<id>，--avatar_id 使用）
- live_avatars.engine_task_id：引擎 Avatar 生成任务 ID（轮询进度用）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"


def upgrade() -> None:
    op.add_column("live_avatars", sa.Column("engine_base_url", sa.Text(), nullable=True))
    op.add_column("live_avatars", sa.Column("engine_avatar_id", sa.String(length=100), nullable=True))
    op.add_column("live_avatars", sa.Column("engine_task_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("live_avatars", "engine_task_id")
    op.drop_column("live_avatars", "engine_avatar_id")
    op.drop_column("live_avatars", "engine_base_url")
