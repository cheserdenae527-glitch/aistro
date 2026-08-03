"""火山引擎豆包 图片生成服务 — Seedream 5.0 流式组图，一次 4 张。"""
from __future__ import annotations

import asyncio
import base64
import io
import json

import httpx
from PIL import Image

from app.core.config import settings

_AVATAR_SIZE = "2048x2048"
_BG_SIZE = "2K"
_EDIT_SIZE = "2K"
_SEQUENTIAL_TAIL = "。请生成4张风格统一、构图和元素略有差异的变体图片。"
_ANCHOR_TAIL = "。生成的图片必须保留锚点图中的核心主体、关键元素与整体配色。"
_MAX_REF_BYTES = 10 * 1024 * 1024
_MAX_REF_DIMENSION = 2048
_STREAM_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class ImageGenError(Exception):
    """豆包生图失败，携带可返回给前端的 HTTP 状态码与提示。"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _file_to_data_url(data: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


def _detect_image_mime(data: bytes) -> str:
    """按实际图片字节返回 MIME，避免 Ark 返回 JPEG 却被标记为 PNG。"""
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format == "PNG":
                return "image/png"
            if img.format in ("JPEG", "MPO"):
                return "image/jpeg"
    # 探测失败时回退默认 MIME
    except Exception:  # nosec B110
        pass
    return "image/png"


def _normalize_ref_image(data: bytes, mime: str = "image/png") -> tuple[bytes, str]:
    """校验并转换参考图为 Seedream 支持的 PNG，限制单张 <=10MB。"""
    if len(data) > _MAX_REF_BYTES:
        raise ImageGenError(status_code=400, detail="参考图超过 10MB 限制")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        converted = img.convert("RGB")
        if max(converted.size) > _MAX_REF_DIMENSION:
            converted.thumbnail(
                (_MAX_REF_DIMENSION, _MAX_REF_DIMENSION),
                Image.Resampling.LANCZOS,
            )
        buf = io.BytesIO()
        converted.save(buf, format="PNG")
        out = buf.getvalue()
    except Exception:
        raise ImageGenError(status_code=400, detail="无法识别的参考图")

    if len(out) > _MAX_REF_BYTES:
        raise ImageGenError(status_code=400, detail="参考图过大，请压缩后重试")
    return out, "image/png"


def _map_http_error(status_code: int, body: bytes) -> ImageGenError:
    """把 Ark 非 200 响应映射成可返回给前端的异常。"""
    message = "火山引擎生图服务返回错误"
    try:
        data = json.loads(body)
        error = data.get("error", {})
        if isinstance(error, dict):
            message = error.get("message") or message
        elif error:
            message = str(error)
    # JSON 解析失败时使用默认错误信息
    except Exception:  # nosec B110
        pass
    message = str(message)[:300]

    if status_code == 400:
        return ImageGenError(status_code=400, detail=message)
    if status_code == 429:
        return ImageGenError(status_code=429, detail="生图服务繁忙，请稍后重试")
    if status_code in (401, 403):
        return ImageGenError(
            status_code=502,
            detail="生图服务鉴权失败，请检查 VOLCENGINE_API_KEY",
        )
    return ImageGenError(status_code=502, detail=message)


def _parse_sse_urls(lines: list[str]) -> list[str]:
    """解析 Ark 流式 SSE，按 image_index 返回图片 URL。"""
    urls_by_index: dict[int, str] = {}
    for line in lines:
        if not line.startswith("data: "):
            continue
        raw = line[6:]
        if raw == "[DONE]":
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        etype = data.get("type", "")
        if etype == "image_generation.partial_succeeded":
            urls_by_index[int(data["image_index"])] = data["url"]
        elif "error" in etype.lower() or "failed" in etype.lower():
            raise ImageGenError(
                status_code=502,
                detail=str(data.get("message") or etype)[:300],
            )

    if not urls_by_index:
        raise ImageGenError(status_code=502, detail="豆包生图流式返回为空")
    return [urls_by_index[i] for i in sorted(urls_by_index)]


async def _stream_image_urls(
    prompt: str,
    size: str,
    ref_data_url: str | None,
) -> list[str]:
    """调用 Seedream 5.0 流式接口，一次生成最多 4 张。"""
    payload: dict = {
        "model": settings.VOLCENGINE_IMAGE_MODEL,
        "prompt": prompt,
        "sequential_image_generation": "auto",
        "sequential_image_generation_options": {"max_images": 4},
        "response_format": "url",
        "size": size,
        "stream": True,
        "watermark": False,
    }
    if ref_data_url:
        payload["image"] = ref_data_url

    headers = {
        "Authorization": f"Bearer {settings.VOLCENGINE_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{settings.VOLCENGINE_BASE_URL}/images/generations"

    lines: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as http:
            async with http.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise _map_http_error(resp.status_code, body)
                async for line in resp.aiter_lines():
                    lines.append(line)
    except ImageGenError:
        raise
    except httpx.HTTPError:
        raise ImageGenError(status_code=502, detail="生图服务连接超时，请稍后重试")

    return _parse_sse_urls(lines)


async def _download_image(url: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            img_resp = await http.get(url)
            img_resp.raise_for_status()
    except httpx.HTTPError:
        raise ImageGenError(status_code=502, detail="豆包图片下载失败")
    return img_resp.content, img_resp.headers.get("content-type", "image/png")


async def generate_avatar(
    prompt: str,
    ref_data: bytes | None = None,
    ref_mime: str = "image/png",
) -> list[tuple[bytes, str]]:
    """生成 4 张头像 -> [(bytes, mime_type), ...]。ref_data 为参考图字节。"""
    return await _generate_image(prompt, _AVATAR_SIZE, ref_data, ref_mime)


async def generate_bg_image(
    prompt: str,
    ref_data: bytes | None = None,
    ref_mime: str = "image/png",
) -> list[tuple[bytes, str]]:
    """生成 4 张背景图 -> [(bytes, mime_type), ...]。"""
    return await _generate_image(prompt, _BG_SIZE, ref_data, ref_mime)


async def generate_edited(
    prompt: str,
    ref_data: bytes | None = None,
    ref_mime: str = "image/png",
) -> list[tuple[bytes, str]]:
    """豆包通用编辑入口 — 纯文生图 / 背景替换 / 菜品增强，一次 4 张候选。"""
    return await _generate_image(prompt, _EDIT_SIZE, ref_data, ref_mime)


async def _generate_image(
    prompt: str,
    size: str,
    ref_data: bytes | None = None,
    ref_mime: str = "image/png",
) -> list[tuple[bytes, str]]:
    ref_data_url = None
    if ref_data:
        normalized_ref = _normalize_ref_image(ref_data, ref_mime)
        ref_data_url = _file_to_data_url(normalized_ref[0], normalized_ref[1])

    prompt_text = prompt + _SEQUENTIAL_TAIL
    if ref_data_url:
        prompt_text += _ANCHOR_TAIL
    urls = await _stream_image_urls(prompt_text, size, ref_data_url)
    results = await asyncio.gather(*(_download_image(url) for url in urls))
    return list(results)
