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
5. 侧重点不变的前提下，每次生成要换一种表达方式和细节侧重，避免两次提示词高度重复
6. 严禁输出 JSON、编号、解释或 markdown
"""

_BG_SYSTEM_PROMPT = """你是一个餐饮场景视觉设计师。只输出一条中文「背景替换」生图提示词正文。

要求：
1. 提示词用于把参考图中的背景替换成新的氛围场景，必须严格保留参考图中的菜品主体、形状、颜色与整体构图
2. 根据用户选择的侧重点强化氛围描述（深夜暖光 / 木质餐桌 / 市井烟火 / 日系干净 / 简约留白 / 高级质感）
3. 描述具体可执行：场景空间、桌面材质、光线方向、背景虚化程度、色彩氛围、氛围道具
4. 100-200 字，可直接交给生图模型
5. 侧重点不变的前提下，每次生成要换一种表达方式和细节侧重，避免两次提示词高度重复
6. 严禁输出 JSON、编号、解释或 markdown
"""

_ENHANCE_SYSTEM_PROMPT = """你是一个美食摄影修图师。只输出一条中文「菜品增强」生图提示词正文。

要求：
1. 提示词用于增强参考图中的菜品，必须保留菜品主体、形状、颜色与整体构图，不改变菜品结构
2. 根据用户选择的侧重点强化对应描述（突出光泽 / 提升质感 / 增强食欲 / 构图饱满 / 细节清晰 / 色彩浓郁）
3. 描述具体可执行：高光、汁水、油脂光泽、纹理细节、摆盘、背景虚化、色彩浓度
4. 100-200 字，可直接交给生图模型
5. 侧重点不变的前提下，每次生成要换一种表达方式和细节侧重，避免两次提示词高度重复
6. 严禁输出 JSON、编号、解释或 markdown
"""

_SYSTEM_BY_KIND = {
    "ai": _BEAUTIFY_SYSTEM_PROMPT,
    "bg": _BG_SYSTEM_PROMPT,
    "enhance": _ENHANCE_SYSTEM_PROMPT,
}

_ACTION_BY_KIND = {
    "ai": "美食图片美化",
    "bg": "背景替换",
    "enhance": "菜品增强",
}


async def generate_edit_prompt(
    kind: str = "ai",
    focus: str | None = None,
    dish_name: str | None = None,
) -> str:
    """生成 AI 编辑提示词，kind 支持 ai / bg / enhance，focus 表明侧重点。"""
    system_prompt = _SYSTEM_BY_KIND.get(kind, _BEAUTIFY_SYSTEM_PROMPT)
    focus_label = (focus or "提升食欲感").strip()
    lines = [f"侧重点：{focus_label}"]
    if dish_name:
        lines.append(f"菜品：{dish_name}")
    lines.append(f"请生成一条{_ACTION_BY_KIND.get(kind, '美食图片美化')}提示词。")

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(lines)},
        ],
        temperature=0.85,
        max_tokens=500,
    )
    raw = response.choices[0].message.content or ""
    clean = std_re.sub(r"```(?:text|markdown)?\s*|\s*```", "", raw).strip()
    clean = std_re.sub(r"^(提示词|美化提示词|背景替换提示词|菜品增强提示词)?[：:]\s*", "", clean)
    return clean[:1000]