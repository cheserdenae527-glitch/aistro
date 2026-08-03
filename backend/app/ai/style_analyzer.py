"""XHS 截图风格分析 — Pillow 取色 + DeepSeek 风格推理。"""
from __future__ import annotations

import io
import json
import re
from collections import Counter
from typing import cast

from openai import AsyncOpenAI
from PIL import Image

from app.core.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


def _extract_dominant_colors(data: bytes, n: int = 6) -> list[str]:
    """从图片提取主色调 hex。"""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = img.resize((100, int(100 * img.height / img.width)))
    if hasattr(img, "get_flattened_data"):
        pixels = cast(list[tuple[int, int, int]], list(img.get_flattened_data()))
    else:
        pixels = cast(list[tuple[int, int, int]], list(img.getdata()))
    counter = Counter(pixels)
    top = [f"#{r:02x}{g:02x}{b:02x}" for (r, g, b), _ in counter.most_common(n)]
    return top


_STYLE_PROMPT = """分析一位小红书博主的个人主页，给出风格分析 JSON：

主页截图提取到的主色调（从多到少）：
{colors}

请推测博主的整体风格，返回 JSON：
{{
  "vibe": "整体风格描述（如：日系清新、高级冷淡、市井烟火、ins风）",
  "dominant_colors": ["主色hex", "辅色hex", "点缀hex", "文字hex"],
  "nickname_style": "昵称风格（如：emoji+店名、纯中文、英文+中文）",
  "bio_style": "简介写作特点",
  "avatar_style": "头像特点（如：logo、真人、食物特写）",
  "bg_style": "背景图特点（如：门头照、食物平铺、纯色）",
  "suggested_prompt": "给豆包生图的英文prompt建议"
}}

只返回 JSON，不要其他文字。"""


async def analyze_style(image_data: bytes, mime: str = "image/png") -> dict:
    """分析截图风格：Pillow 取色 + DeepSeek 推理。"""
    # 1. 取色
    colors = _extract_dominant_colors(image_data)
    color_list = ", ".join(colors)

    # 2. LLM 推理
    client = _get_client()
    prompt = _STYLE_PROMPT.format(colors=color_list)

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        timeout=20,
    )

    raw = response.choices[0].message.content or "{}"
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {
        "vibe": "未能识别",
        "dominant_colors": colors[:4],
        "suggested_prompt": "warm restaurant storefront, natural lighting",
    }
