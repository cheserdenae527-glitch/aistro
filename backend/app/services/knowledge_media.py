"""知识库媒体本地化 — 学习 Beav：扩展只传 URL，后端下载图片/视频到本地存储。

保存形式对齐 Beav：每条知识有独立本地媒体（封面/图片/视频），
前端通过 /api/v1/media/<object> 直接浏览，不依赖上游 CDN。
"""
from __future__ import annotations

import uuid
from urllib.parse import urlparse

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_entry import KnowledgeEntry
from app.services import storage

_ALLOWED_HOST_SUFFIXES = ("xiaohongshu.com", "xhscdn.com", "xhslink.com")
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_VIDEO_BYTES = 300 * 1024 * 1024
_TIMEOUT = 20


def _is_allowed(url: str) -> bool:
    try:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        return any(host == s or host.endswith("." + s) for s in _ALLOWED_HOST_SUFFIXES)
    except Exception:
        return False


def _download(url: str, max_bytes: int) -> tuple[bytes | None, str]:
    if not _is_allowed(url):
        return None, ""
    try:
        with requests.get(
            url,
            headers={"Referer": "https://www.xiaohongshu.com/"},
            timeout=_TIMEOUT,
            allow_redirects=True,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                return None, ""
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            data = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data) > max_bytes:
                    return None, ""
    except Exception:
        return None, ""
    return bytes(data), ctype


def _image_ext(ctype: str) -> str:
    if "png" in ctype:
        return "png"
    if "gif" in ctype:
        return "gif"
    return "jpg"


def _save(data: bytes, folder: str, filename: str) -> str | None:
    try:
        obj = f"{folder}/{filename}"
        path = storage.write_path(obj)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return obj
    except Exception:
        return None


def _media_urls(note: dict) -> dict:
    return {
        "image_urls": [u for u in (note.get("image_urls") or []) if isinstance(u, str) and u],
        "cover_url": str(note.get("cover_url") or ""),
        "video_url": str(note.get("video_url") or ""),
    }


async def attach_entry_media(db: AsyncSession, entry: KnowledgeEntry, note: dict) -> dict:
    """下载封面/图片/视频到本地并更新 entry。失败静默跳过，保留远程 URL 兜底。"""
    result = {"images": 0, "video": False}
    media = _media_urls(note)
    folder = f"knowledge/{entry.id}"

    if not entry.cover_local and media["cover_url"]:
        data, ctype = _download(media["cover_url"], _MAX_IMAGE_BYTES)
        if data:
            obj = _save(data, folder, f"cover-{uuid.uuid4().hex[:8]}.{_image_ext(ctype)}")
            if obj:
                entry.cover_local = obj

    local_images: list[str] = []
    for url in media["image_urls"]:
        data, ctype = _download(url, _MAX_IMAGE_BYTES)
        if not data:
            continue
        obj = _save(data, folder, f"image-{uuid.uuid4().hex[:8]}.{_image_ext(ctype)}")
        if obj:
            local_images.append(obj)
    if local_images:
        entry.image_urls_local = local_images
        result["images"] = len(local_images)

    if not entry.video_local and media["video_url"]:
        data, ctype = _download(media["video_url"], _MAX_VIDEO_BYTES)
        if data:
            obj = _save(data, folder, "video.mp4")
            if obj:
                entry.video_local = obj
                result["video"] = True

    return result


async def backfill_entry_media(db: AsyncSession, entry: KnowledgeEntry) -> dict:
    """为已入库但缺少本地媒体的条目补下载封面/图片/视频。"""
    note = {
        "cover_url": entry.cover_url or "",
        "image_urls": entry.image_urls or [],
        "video_url": entry.video_url or "",
    }
    return await attach_entry_media(db, entry, note)
