"""图片工具 — HEIC/HEIF 识别与统一转码，支持手机截图直接上传。"""
from __future__ import annotations

import io

from PIL import Image

_heif_ready = False

HEIF_MIMES = {
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
}


def ensure_heif_support() -> None:
    """注册 Pillow 的 HEIC/HEIF 解码能力（仅首次调用生效）。"""
    global _heif_ready
    if _heif_ready:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass
    _heif_ready = True


def normalize_image_bytes(data: bytes, mime: str) -> tuple[bytes, str]:
    """把 HEIC/HEIF 手机截图转成 PNG；其他格式原样返回。

    返回 (bytes, mime)，供上传、参考图、视觉分析统一使用。
    """
    ensure_heif_support()
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        if fmt in ("HEIC", "HEIF") or (mime or "").lower() in HEIF_MIMES:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue(), "image/png"
    except Exception:
        pass
    return data, mime or "image/png"
