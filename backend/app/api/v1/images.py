"""图片代理 — 下载 XHS 图片并转发，绕过 CDN 尺寸限制。"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image

from app.core.rate_limit import consume_rate_limit

router = APIRouter(prefix="/images", tags=["images"])

_ALLOWED_HOST_SUFFIXES = ("xiaohongshu.com", "xhscdn.com", "xhslink.com")
_MAX_PROXY_BYTES = 20 * 1024 * 1024
_MAX_RESIZE_WIDTH = 4096
_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "storage" / "image_proxy_cache"


def _cache_paths(url: str, size: int) -> tuple[Path, Path]:
    key = hashlib.sha256(f"{url}:{size}".encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{key}.img", _CACHE_DIR / f"{key}.json"


def _read_cache(url: str, size: int) -> tuple[bytes, str] | None:
    cache_path, meta_path = _cache_paths(url, size)
    try:
        if not (cache_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return cache_path.read_bytes(), meta.get("content_type", "application/octet-stream")
    except Exception:
        return None


def _write_cache(url: str, size: int, content: bytes, content_type: str) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path, meta_path = _cache_paths(url, size)
        cache_path.write_bytes(content)
        meta_path.write_text(json.dumps({"content_type": content_type}), encoding="utf-8")
    except Exception:
        pass


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
    cached = _read_cache(url, size)
    if cached is not None:
        return Response(content=cached[0], media_type=cached[1], headers={"Cache-Control": "public, max-age=86400"})
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
        _write_cache(url, size, image_bytes, content_type)
        return Response(content=image_bytes, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="image proxy failed")


@router.get("/video-proxy")
async def proxy_video(
    request: Request,
    url: str = Query(""),
    download: int = Query(0),
):
    """代理流式转发 XHS 视频。download=0 内联播放；download=1 附件下载，不跳转页面。"""
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    url = unquote(url)
    if not _is_allowed_image_url(url):
        raise HTTPException(status_code=400, detail="url not allowed")
    ip = request.client.host if request.client else "unknown"
    if not await consume_rate_limit(f"video_proxy:{ip}", 30, 60):
        raise HTTPException(status_code=429, detail="请求过于频繁")
    try:
        upstream_headers = {"Referer": "https://www.xiaohongshu.com/"}
        status_code = 200
        resp_headers = {"Cache-Control": "public, max-age=3600", "Accept-Ranges": "bytes"}
        range_header = request.headers.get("range")
        if range_header:
            upstream_headers["Range"] = range_header
        upstream = requests.get(
            url,
            headers=upstream_headers,
            timeout=15,
            allow_redirects=True,
            stream=True,
        )
        upstream.raise_for_status()
        content_type = upstream.headers.get("content-type", "") or "video/mp4"
        if range_header and upstream.status_code == 206:
            status_code = 206
            resp_headers["Content-Range"] = upstream.headers.get("content-range", "")
            resp_headers["Content-Length"] = upstream.headers.get("content-length", "")
        elif upstream.headers.get("content-length"):
            resp_headers["Content-Length"] = upstream.headers["content-length"]
        if download == 1:
            resp_headers["Content-Disposition"] = 'attachment; filename="xhs_video.mp4"'
        return StreamingResponse(
            upstream.iter_content(chunk_size=64 * 1024),
            status_code=status_code,
            media_type=content_type,
            headers=resp_headers,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="video proxy failed")

