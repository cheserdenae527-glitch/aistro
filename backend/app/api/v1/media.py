"""本地媒体文件服务 — 替代 MinIO 预签名 URL 的直接访问。"""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.storage import resolve_object

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{object_name:path}")
async def get_media(object_name: str):
    """按 object_name 读取本地媒体文件（图片/视频），支持 Range。"""
    try:
        path = resolve_object(object_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid object name") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)