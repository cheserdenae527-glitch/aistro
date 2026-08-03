"""视觉设计 AI 提示词生成 — 基于 DeepSeek LLM。"""
from __future__ import annotations

import re as std_re

from openai import AsyncOpenAI

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


_BEAUTIFY_SYSTEM_PROMPT = """你是一个餐饮视觉设计师。只输出一条中文「美食图片美化」生图提示词正文。

要求：
1. 提示词用于对参考图进行高级美食摄影美化，必须包含：保留参考图中的菜品主体、形状、颜色与整体构图，不要改变菜品结构
2. 根据用户选择的侧重点强化对应描述（暖色氛围 / 突出食材 / 提升食欲 / 日系干净 / 构图留白 / 高级质感）
3. 描述具体可执行：光影层次、食物光泽与质感、色彩氛围、背景氛围、构图细节
4. 100-200 字，可直接交给生图模型
5. 严禁输出 JSON、编号、解释或 markdown
"""


async def generate_beautify_prompt(
    focus: str | None = None,
    dish_name: str | None = None,
) -> str:
    """生成 AI 一键美化的提示词，focus 表明侧重点。"""
    focus_label = (focus or "提升食欲感").strip()
    lines = [f"侧重点：{focus_label}"]
    if dish_name:
        lines.append(f"菜品：{dish_name}")
    lines.append("请生成一条美食图片美化提示词。")

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _BEAUTIFY_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ],
        temperature=0.9,
        max_tokens=500,
    )
    raw = response.choices[0].message.content or ""
    clean = std_re.sub(r"```(?:text|markdown)?\s*|\s*```", "", raw).strip()
    clean = std_re.sub(r"^(提示词|美化提示词)?[：:]\s*", "", clean)
    return clean[:1000]
