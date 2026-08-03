"""一键美化管线 — Pillow 纯函数，默认保留中餐暖光色调。"""
from __future__ import annotations

import io

from PIL import Image, ImageEnhance, ImageFilter, ImageStat


def _gray_world_white_balance(img: Image.Image) -> Image.Image:
    """灰度世界白平衡：仅当用户显式开启 color_correct 时使用。"""
    r_mean, g_mean, b_mean = ImageStat.Stat(img).mean[:3]
    if r_mean <= 0 or g_mean <= 0 or b_mean <= 0:
        return img
    avg = (r_mean + g_mean + b_mean) / 3.0
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * avg / r_mean)))
    g = g.point(lambda x: min(255, int(x * avg / g_mean)))
    b = b.point(lambda x: min(255, int(x * avg / b_mean)))
    return Image.merge("RGB", (r, g, b))


def auto_beautify(
    data: bytes,
    mode: str = "enhance",
    brightness: float = 1.05,
    contrast: float = 1.08,
    saturation: float = 1.05,
    white_balance: bool | None = None,
    quality: int = 85,
) -> bytes:
    """Pillow 一键美化管线 -> JPEG bytes。

    mode=enhance（默认）：不做灰度世界白平衡，保留暖光色调。
    mode=color_correct：显式执行白平衡。
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")

    if white_balance is None:
        white_balance = mode == "color_correct"
    if white_balance:
        img = _gray_world_white_balance(img)

    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Color(img).enhance(saturation)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=3))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
