"""认证 API：注册 / 登录 / 当前用户。"""

from __future__ import annotations

import ipaddress
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import Token, UserLogin, UserRegister, UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_ATTEMPTS = 200
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _check_login_rate(email: str, ip: str) -> bool:
    """进程内滑动窗口限流，避免同一账号被暴力撞库。"""
    key = f"{email}|{ip}"
    now = time.monotonic()
    with _login_lock:
        attempts = [
            t
            for t in _login_attempts.get(key, [])
            if now - t < _LOGIN_WINDOW_SECONDS
        ]
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            return False
        attempts.append(now)
        _login_attempts[key] = attempts
        return True


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> Token:
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    if not _check_login_rate(f"register:{email}", ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="注册过于频繁，请稍后再试",
        )
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    db.add(user)
    await db.flush()
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token, user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    if not _check_login_rate(email, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="尝试过于频繁，请稍后再试",
        )
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token, user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """更新当前用户信息：姓名、密码（本地内部工具，无需旧密码）。"""
    if body.name:
        current_user.name = body.name
    if body.new_password:
        current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)

def _is_loopback_client(ip: str) -> bool:
    if ip == "testclient":  # pytest TestClient
        return True
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


@router.post("/local-login", response_model=Token)
async def local_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """本地内部工具免登录：自动创建/复用本地管理员并签发 token。"""
    if not settings.LOCAL_AUTO_LOGIN:
        raise HTTPException(status_code=403, detail="本地免登录未开启")
    ip = request.client.host if request.client else ""
    if not _is_loopback_client(ip):
        raise HTTPException(status_code=403, detail="仅允许本机免登录")
    email = settings.LOCAL_ADMIN_EMAIL.lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            name=settings.LOCAL_ADMIN_NAME,
            role="admin",
        )
        db.add(user)
        await db.flush()
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token, user=UserResponse.model_validate(user)
    )
