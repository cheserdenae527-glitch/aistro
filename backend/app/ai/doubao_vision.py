"""豆包视觉模型 — 主页截图风格识别，输出色系与多套参考方案。"""
from __future__ import annotations

import base64
import io
import json
import re

import httpx
from PIL import Image

from app.ai.style_analyzer import _extract_dominant_colors, analyze_style
from app.core.config import settings
from app.services.xhs_knowledge import enrich_clone_schemes

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_VISION_PROMPT = """你是小红书主页装修设计师。识别这张小红书个人主页/店铺页截图，输出风格分析 JSON。

要求：
1. 只基于图片内容判断，不编造图片里没有的信息
2. dominant_colors：从图片提取 4 个主色 hex（主色/辅色/点缀/文字）
3. schemes：给出 3 套完整参考方案，每套包含色系、风格关键词、昵称候选、简介、头像提示词、背景提示词
   - 色系要与原图风格接近但各有差异（如更暖、更清爽、更高级）
   - 昵称 <=20 字、无 emoji；简介 <=100 字、含服务对象和下一步动作
   - 头像/背景提示词用中文，符合门店定位和该套色系
4. 只输出 JSON（无代码块标记）：
{"vibe":"整体风格一句话","dominant_colors":["#...","#..."],"style_keywords":["..."],"schemes":[{"id":"A","name":"方案名","color_scheme":{"primary":"#...","secondary":"#...","accent":"#...","text":"#..."},"style_keywords":["..."],"nickname_options":["a","b","c"],"bio":"...","avatar_prompt":"...","bg_prompt":"..."}]}"""


def _normalize_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """转码 HEIC 并限制图片尺寸，降低视觉接口传输体积。"""
    from app.services.image_utils import normalize_image_bytes

    data, mime = normalize_image_bytes(data, mime)
    try:
        img = Image.open(io.BytesIO(data))
        if max(img.size) > 1024:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        fmt = "JPEG" if img.format in ("JPEG", "MPO") else "PNG"
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format=fmt)
        return buf.getvalue(), "image/jpeg" if fmt == "JPEG" else "image/png"
    except Exception:
        return data, mime or "image/png"


def _to_data_url(data: bytes, mime: str) -> str:
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


async def _call_vision(image_data: bytes, mime: str) -> str:
    """调用豆包视觉 responses 接口，返回助手文本。"""
    data, mime = _normalize_image(image_data, mime)
    payload = {
        "model": settings.VOLCENGINE_VISION_MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": _to_data_url(data, mime)},
                    {"type": "input_text", "text": _VISION_PROMPT},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.VOLCENGINE_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{settings.VOLCENGINE_BASE_URL}/responses"

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()

    for item in body.get("output") or []:
        if item.get("type") == "message" and item.get("role") == "assistant":
            texts = [
                c.get("text", "")
                for c in item.get("content") or []
                if c.get("type") == "output_text"
            ]
            if texts:
                return texts[0]
    return "{}"


def _parse_style_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


def _clean_hex_list(items, limit: int = 4) -> list[str]:
    out: list[str] = []
    for x in items or []:
        s = str(x).strip()
        if _HEX_RE.match(s) and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _normalize_result(data: dict, fallback_colors: list[str]) -> dict:
    """把视觉模型 JSON 规整成前端可用的结构，缺失字段降级。"""
    schemes: list[dict] = []
    for s in (data.get("schemes") or [])[:3]:
        if not isinstance(s, dict):
            continue
        cs = s.get("color_scheme") or {}
        colors = _clean_hex_list(
            [cs.get("primary"), cs.get("secondary"), cs.get("accent"), cs.get("text")],
            4,
        )
        if len(colors) != 4:
            continue
        scheme_id = str(s.get("id") or chr(65 + len(schemes)))
        schemes.append(
            {
                "id": scheme_id,
                "name": str(s.get("name") or f"方案{scheme_id}")[:30],
                "color_scheme": {
                    "primary": colors[0],
                    "secondary": colors[1],
                    "accent": colors[2],
                    "text": colors[3],
                },
                "style_keywords": [str(k).strip()[:20] for k in (s.get("style_keywords") or [])][:6],
                "nickname_options": [
                    str(n).strip()[:20]
                    for n in (s.get("nickname_options") or [])
                    if str(n).strip()
                ][:3],
                "bio": str(s.get("bio") or "").strip()[:100],
                "avatar_prompt": str(s.get("avatar_prompt") or "").strip()[:1000],
                "bg_prompt": str(s.get("bg_prompt") or "").strip()[:1000],
            }
        )

    first_avatar = schemes[0]["avatar_prompt"] if schemes else ""
    return {
        "vibe": str(data.get("vibe") or "未能识别")[:100],
        "dominant_colors": _clean_hex_list(data.get("dominant_colors"), 4) or fallback_colors[:4],
        "style_keywords": [str(k).strip()[:20] for k in (data.get("style_keywords") or [])][:8],
        "nickname_style": str(data.get("nickname_style") or "")[:50],
        "bio_style": str(data.get("bio_style") or "")[:100],
        "avatar_style": str(data.get("avatar_style") or "")[:50],
        "bg_style": str(data.get("bg_style") or "")[:50],
        "suggested_prompt": str(data.get("suggested_prompt") or first_avatar)[:1000],
        "schemes": schemes,
    }


async def analyze_image_style(image_data: bytes, mime: str = "image/png") -> dict:
    """豆包视觉识别主页截图风格，返回色系 + 多套参考方案。"""
    try:
        fallback_colors = _extract_dominant_colors(image_data)
    except Exception:
        fallback_colors = []
    raw = await _call_vision(image_data, mime)
    data = _parse_style_json(raw)
    return _normalize_result(data, fallback_colors)


async def analyze_clone_style_with_fallback(
    image_data: bytes, mime: str = "image/png"
) -> dict:
    """优先豆包视觉；识别失败或没有多方案时回退旧 DeepSeek 分析。"""
    try:
        result = await analyze_image_style(image_data, mime)
        if result.get("schemes"):
            return enrich_clone_schemes(result)
    except Exception:
        pass
    return await analyze_style(image_data, mime)
