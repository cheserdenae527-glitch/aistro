"""菜单渲染服务 — 纯函数：配置 + 素材字节 -> PNG 字节。

模板：xhs_menu_01（1242x1660）、a4_menu_01（2480x3508）。
字体统一使用仓库内 Noto Sans SC，保证本地与 Docker 渲染一致。
"""
from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REGULAR_FONT = FONT_DIR / "NotoSansSC-Regular.otf"
BOLD_FONT = FONT_DIR / "NotoSansSC-Bold.otf"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT if bold else REGULAR_FONT
    return ImageFont.truetype(str(path), size)


def _get_attr(asset, name: str):
    if isinstance(asset, dict):
        return asset.get(name)
    return getattr(asset, name, None)


def resolve_item(item: dict, asset) -> dict:
    """渲染取值：override_* 优先于素材库字段。"""
    price = item.get("override_price")
    if price is None:
        price = _get_attr(asset, "price")
    return {
        "asset_id": str(item["asset_id"]),
        "section": item.get("section") or "招牌",
        "sort": item.get("sort", 0),
        "name": item.get("override_name") or _get_attr(asset, "dish_name") or "招牌菜",
        "price": str(price) if price is not None else None,
        "tagline": item.get("override_tagline") or _get_attr(asset, "tagline") or "",
    }


def _load_image(data: bytes, size: tuple[int, int]) -> Image.Image:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return _cover(img, size)


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    iw, ih = img.size
    scale = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255
    )
    return mask


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    center_x: float,
    y: float,
    fill,
) -> None:
    width = _text_w(draw, text, font)
    draw.text((center_x - width / 2, y), text, font=font, fill=fill)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_xhs(config: dict, asset_images: dict[str, bytes]) -> bytes:
    width, height = 1242, 1660
    scheme = config.get("color_scheme") or {}
    primary = scheme.get("primary", "#D4520A")
    secondary = scheme.get("secondary", "#FFF6EC")
    text_color = scheme.get("text", "#2D1A0A")

    img = Image.new("RGB", (width, height), secondary)
    draw = ImageDraw.Draw(img)

    shop_name = config.get("shop_name") or "本店菜单"
    _draw_centered(draw, shop_name, _font(72, bold=True), width / 2, 72, text_color)
    draw.line([200, 210, width - 200, 210], fill=primary, width=3)

    card_w, gap = 560, 40
    left, start_y, img_h, row_h = 60, 250, 373, 470
    items = (config.get("items") or [])[:6]

    for idx, item in enumerate(items):
        row, col = divmod(idx, 2)
        x = left + col * (card_w + gap)
        y = start_y + row * row_h
        card_h = 452
        draw.rounded_rectangle(
            [x, y, x + card_w, y + card_h], radius=18, fill="#FFFFFF",
            outline=primary, width=2,
        )

        data = asset_images.get(item["asset_id"])
        if data:
            dish = _load_image(data, (card_w - 24, img_h))
            img.paste(dish, (x + 12, y + 12), _rounded_mask(dish.size, 14))

        name = item.get("name") or "招牌菜"
        name_font = _font(38, bold=True)
        max_name_w = card_w - 180
        while name and _text_w(draw, name, name_font) > max_name_w:
            name = name[:-1]
        draw.text((x + 20, y + img_h + 22), name, font=name_font, fill=text_color)

        price = item.get("price")
        if price:
            price_font = _font(34, bold=True)
            price_text = f"¥{price}"
            draw.text(
                (x + card_w - 20 - _text_w(draw, price_text, price_font), y + img_h + 26),
                price_text,
                font=price_font,
                fill=primary,
            )

        tagline = item.get("tagline") or ""
        if tagline:
            draw.text(
                (x + 20, y + img_h + 84),
                tagline[:20],
                font=_font(26),
                fill=(126, 96, 76),
            )

    return _png_bytes(img)


def _render_a4(config: dict, asset_images: dict[str, bytes]) -> bytes:
    width, height = 2480, 3508
    scheme = config.get("color_scheme") or {}
    primary = scheme.get("primary", "#C93828")
    text_color = scheme.get("text", "#2A0A08")

    img = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    shop_name = config.get("shop_name") or "本店菜单"
    _draw_centered(draw, shop_name, _font(140, bold=True), width / 2, 120, text_color)
    draw.rectangle([420, 350, width - 420, 358], fill=primary)

    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for item in config.get("items") or []:
        section = item.get("section") or "招牌"
        groups.setdefault(section, []).append(item)

    card_w, gap = 1080, 80
    left, img_h, row_h = 160, 420, 640
    y = 430
    for section, items in groups.items():
        if y > height - 260:
            break
        _draw_centered(draw, section, _font(82, bold=True), width / 2, y, primary)
        y += 150
        for idx, item in enumerate(items[:12]):
            row, col = divmod(idx, 2)
            x = left + col * (card_w + gap)
            yy = y + row * row_h
            if yy + row_h - 170 > height - 60:
                break
            draw.rounded_rectangle(
                [x, yy, x + card_w, yy + row_h - 170], radius=20,
                fill="#FFFDF9", outline=primary, width=3,
            )
            data = asset_images.get(item["asset_id"])
            if data:
                dish = _load_image(data, (card_w - 32, img_h))
                img.paste(dish, (x + 16, yy + 16), _rounded_mask(dish.size, 16))

            name = item.get("name") or "招牌菜"
            name_font = _font(48, bold=True)
            max_name_w = card_w - 260
            while name and _text_w(draw, name, name_font) > max_name_w:
                name = name[:-1]
            draw.text((x + 24, yy + img_h + 30), name, font=name_font, fill=text_color)

            price = item.get("price")
            if price:
                price_font = _font(44, bold=True)
                price_text = f"¥{price}"
                draw.text(
                    (
                        x + card_w - 24 - _text_w(draw, price_text, price_font),
                        yy + img_h + 38,
                    ),
                    price_text,
                    font=price_font,
                    fill=primary,
                )

            tagline = item.get("tagline") or ""
            if tagline:
                draw.text(
                    (x + 24, yy + img_h + 102),
                    tagline[:30],
                    font=_font(34),
                    fill=(100, 80, 60),
                )
        y += ((len(items) + 1) // 2) * row_h

    return _png_bytes(img)


def render_menu(config: dict, asset_images: dict[str, bytes]) -> bytes:
    """纯函数渲染：config + asset_id -> bytes 的素材字典 -> PNG bytes。"""
    template_id = config.get("template_id")
    if template_id == "xhs_menu_01":
        return _render_xhs(config, asset_images)
    if template_id == "a4_menu_01":
        return _render_a4(config, asset_images)
    raise ValueError(f"未知模板: {template_id}")
