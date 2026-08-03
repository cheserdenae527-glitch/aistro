"""Pytest 配置 — 使用独立测试数据库，提供 authenticated TestClient。"""
from __future__ import annotations

import asyncio
import os

# 必须在导入 app 前设置，测试永远不写正式数据库。
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://aistro:aistro@localhost:5433/aistro_test",
)
os.environ["REDIS_URL"] = os.environ.get(
    "TEST_REDIS_URL",
    "redis://:aistro-redis-dev@127.0.0.1:6379/0",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _init_test_database():
    """每次测试会话重建 aistro_test 表结构，下一轮自动覆盖。"""
    engine = create_async_engine(os.environ["DATABASE_URL"])

    async def reset() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    """共享同一个 TestClient，避免跨模块轮换事件循环导致连接池失效。"""
    with TestClient(app) as c:
        yield c
