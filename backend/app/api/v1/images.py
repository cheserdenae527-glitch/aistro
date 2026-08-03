"""图片代理 — 下载 XHS 图片并转发，绕过 CDN 尺寸限制。"""
from __future__ import annotations

import io
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from PIL import Image

from app.core.rate_limit import consume_rate_limit

router = APIRouter(prefix="/images", tags=["images"])

_ALLOWED_HOST_SUFFIXES = ("xiaohongshu.com", "xhscdn.com", "xhslink.com")
_MAX_PROXY_BYTES = 20 * 1024 * 1024
_MAX_RESIZE_WIDTH = 4096


def _is_allowed_image_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


@router.get("/proxy")
async def proxy_image(
    request: Request,
    url: str = Query(""),
    size: int = Query(0),
):
    """代理下载并转发图片。size=0 原图，>0 放大到指定宽度（保持比例）。"""
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    url = unquote(url)
    if not _is_allowed_image_url(url):
        raise HTTPException(status_code=400, detail="url not allowed")
    if size < 0 or size > _MAX_RESIZE_WIDTH:
        raise HTTPException(status_code=400, detail="invalid size")
    ip = request.client.host if request.client else "unknown"
    if not await consume_rate_limit(f"image_proxy:{ip}", 60, 60):
        raise HTTPException(status_code=429, detail="请求过于频繁")
    try:
        with requests.get(
            url,
            headers={"Referer": "https://www.xiaohongshu.com/"},
            timeout=10,
            allow_redirects=False,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="image proxy failed")
            content_type = resp.headers.get('content-type', '')
            if not content_type.lower().startswith('image/'):
                raise HTTPException(status_code=400, detail="url is not an image")
            raw_data = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                raw_data.extend(chunk)
                if len(raw_data) > _MAX_PROXY_BYTES:
                    raise HTTPException(status_code=502, detail="image too large")
            image_bytes = bytes(raw_data)
        if size > 0:
            img = Image.open(io.BytesIO(image_bytes))
            ratio = size / img.width
            new_h = int(img.height * ratio)
            resized = img.resize((size, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format='JPEG', quality=85)
            image_bytes = buf.getvalue()
            content_type = 'image/jpeg'
        return Response(content=image_bytes, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="image proxy failed")
