"""AiRestro API 入口。"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services'))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import routers
from app.core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动时：连接池自动由 SQLAlchemy 管理
    yield
    # 关闭时：引擎清理
    from app.core.database import engine

    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in routers:
    app.include_router(r, prefix="/api/v1")


@app.get("/ping")
async def ping():
    return {"status": "ok"}


