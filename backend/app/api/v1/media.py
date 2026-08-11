"""本地媒体文件服务 — 替代 MinIO 预签名 URL 的直接访问（支持 Range 视频播放）。"""
from __future__ import annotations

import mimetypes
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.storage import resolve_object

router = APIRouter(prefix="/media", tags=["media"])

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@router.get("/{object_name:path}")
async def get_media(object_name: str, range: str | None = None):
    """按 object_name 读取本地媒体文件（图片/视频），支持 HTTP Range 分段播放。"""
    try:
        path = resolve_object(object_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid object name") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    size = path.stat().st_size

    if range:
        match = _RANGE_RE.match(range)
        if match:
            start_raw, end_raw = match.groups()
            start = int(start_raw) if start_raw else 0
            end = int(end_raw) if end_raw else size - 1
            if start >= size:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{size}"},
                )
            end = min(end, size - 1)
            if start > end:
                start, end = 0, size - 1
            with path.open("rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            return Response(
                content=data,
                status_code=206,
                media_type=media_type,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Length": str(len(data)),
                },
            )
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        headers={"Accept-Ranges": "bytes"},
    )
