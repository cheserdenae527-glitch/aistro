"""图片代理 — 下载 XHS 图片并转发，绕过 CDN 尺寸限制。"""
from __future__ import annotations

import io
from urllib.parse import unquote

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/proxy")
async def proxy_image(
    url: str = Query(""),
    size: int = Query(0),
):
    """代理下载并转发图片。size=0 原图，>0 放大到指定宽度（保持比例）。"""
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    url = unquote(url)
    if not url.startswith('http'):
        raise HTTPException(status_code=400, detail="invalid url")
    try:
        resp = requests.get(url, headers={"Referer": "https://www.xiaohongshu.com/"}, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', 'image/webp')
        data = resp.content
        if size > 0:
            img = Image.open(io.BytesIO(data))
            ratio = size / img.width
            new_h = int(img.height * ratio)
            img = img.resize((size, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            data = buf.getvalue()
            content_type = 'image/jpeg'
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"proxy failed: {e}")
