"""设置 API — 文件保存位置、文字/图片/视频 API 密钥。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.settings import ApiKeyStatus, SettingsResponse, SettingsUpdate
from app.services import runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _mask(key: str) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return f"{key[:5]}****{key[-4:]}"


def _status(api_key: str, base_url: str, model: str) -> ApiKeyStatus:
    return ApiKeyStatus(
        configured=bool(api_key),
        preview=_mask(api_key),
        base_url=base_url or "",
        model=model or "",
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    data = runtime_settings.get()
    dirs = data.get("storage_dirs") or []
    return SettingsResponse(
        storage={
            "current_dir": settings.LOCAL_STORAGE_DIR,
            "dirs": dirs,
            "default_dir": settings.LOCAL_STORAGE_DIR,
        },
        text=_status(
            data.get("deepseek_api_key", ""),
            data.get("deepseek_base_url", ""),
            data.get("deepseek_model", ""),
        ),
        image=_status(
            data.get("volcengine_api_key", ""),
            data.get("volcengine_base_url", ""),
            data.get("volcengine_image_model", ""),
        ),
        vision=_status(
            data.get("volcengine_api_key", ""),
            data.get("volcengine_base_url", ""),
            data.get("volcengine_vision_model", ""),
        ),
        video=_status(
            data.get("video_api_key", ""),
            data.get("video_api_base_url", ""),
            data.get("video_api_model", ""),
        ),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    patch: dict = {}
    if body.storage_dir is not None:
        patch["storage_dir"] = body.storage_dir

    def merge(mapping: dict) -> None:
        for key, value in mapping.items():
            if value is not None:
                patch[key] = value

    if body.text is not None:
        merge(
            {
                "deepseek_api_key": body.text.api_key,
                "deepseek_base_url": body.text.base_url,
                "deepseek_model": body.text.model,
            }
        )
    if body.image is not None:
        merge(
            {
                "volcengine_api_key": body.image.api_key,
                "volcengine_base_url": body.image.base_url,
                "volcengine_image_model": body.image.model,
            }
        )
    if body.vision is not None:
        merge(
            {
                "volcengine_api_key": body.vision.api_key,
                "volcengine_base_url": body.vision.base_url,
                "volcengine_vision_model": body.vision.model,
            }
        )
    if body.video is not None:
        merge(
            {
                "video_api_key": body.video.api_key,
                "video_api_base_url": body.video.base_url,
                "video_api_model": body.video.model,
            }
        )
    if not patch:
        raise HTTPException(status_code=400, detail="没有可保存的设置")
    data = runtime_settings.save(patch)
    dirs = data.get("storage_dirs") or []
    return SettingsResponse(
        storage={
            "current_dir": settings.LOCAL_STORAGE_DIR,
            "dirs": dirs,
            "default_dir": settings.LOCAL_STORAGE_DIR,
        },
        text=_status(
            data.get("deepseek_api_key", ""),
            data.get("deepseek_base_url", ""),
            data.get("deepseek_model", ""),
        ),
        image=_status(
            data.get("volcengine_api_key", ""),
            data.get("volcengine_base_url", ""),
            data.get("volcengine_image_model", ""),
        ),
        vision=_status(
            data.get("volcengine_api_key", ""),
            data.get("volcengine_base_url", ""),
            data.get("volcengine_vision_model", ""),
        ),
        video=_status(
            data.get("video_api_key", ""),
            data.get("video_api_base_url", ""),
            data.get("video_api_model", ""),
        ),
    )