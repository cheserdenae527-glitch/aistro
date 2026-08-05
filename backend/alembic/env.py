"""Alembic 异步迁移环境配置。"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models import (  # noqa: F401
    User, Merchant, Shop, PlatformShop, Review, MenuItem, CrawlJob, Report,
    ManualImport, ShopProfile, DesignProject, DesignAsset, MenuDesign, DesignJob,
    MenuDesignVersion, StudioProject, StudioCopy, StudioDeck, DistrictSnapshot,
    DistrictPoi, DistrictPoiOverride, DealProject, DealItem, CompetitorDeal,
    DealScheme, DealSchemeCopy, LiveProject, LiveAvatar, LiveScript,
    LiveDanmakuConfig, LiveSession, LiveSessionMetric,
)

config = context.config

if config.config_file_name is not None:
   fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
   url = settings.DATABASE_URL
   context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
   with context.begin_transaction():
       context.run_migrations()


def do_run_migrations(connection):
   context.configure(connection=connection, target_metadata=target_metadata)
   with context.begin_transaction():
       context.run_migrations()


async def run_async_migrations() -> None:
   url = settings.DATABASE_URL
   connect_args = {}
   search_path = config.get_main_option("sqlalchemy_search_path")
   if search_path:
       connect_args["server_settings"] = {"search_path": search_path}
   connectable = create_async_engine(url, connect_args=connect_args)
   async with connectable.connect() as connection:
       await connection.run_sync(do_run_migrations)
   await connectable.dispose()


def run_migrations_online() -> None:
   asyncio.run(run_async_migrations())


if context.is_offline_mode():
   run_migrations_offline()
else:
   run_migrations_online()





