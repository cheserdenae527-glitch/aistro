"""AiRestro API 入口。"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services'))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import routers
from app.core.config import settings


_subscription_scheduler = None
_cookie_scheduler = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _subscription_scheduler
    # 启动时：连接池自动由 SQLAlchemy 管理；订阅定时刷新从 subscriptions 表重建调度
    from app.services.subscription_scheduler import SubscriptionScheduler

    _subscription_scheduler = SubscriptionScheduler()
    _subscription_scheduler.start()
    from app.services.cookie_health_scheduler import CookieHealthScheduler

    global _cookie_scheduler
    _cookie_scheduler = CookieHealthScheduler()
    _cookie_scheduler.start()
    yield
    # 关闭时：停止调度器并清理引擎
    if _subscription_scheduler is not None:
        _subscription_scheduler.shutdown()
    if _cookie_scheduler is not None:
        _cookie_scheduler.shutdown()
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


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy", "strict-origin-when-cross-origin"
    )
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


for r in routers:
    app.include_router(r, prefix="/api/v1")


@app.get("/ping")
async def ping():
    return {"status": "ok"}


