"""StudioImagePromptAgent — 把配图指导方向提炼并丰富成完整生图提示词。

流程：先提炼配图指导的核心想法（主体/氛围/用途），再结合门店信息与文案背景，
扩写成可直接交给生图模型（豆包/即梦）的专业中文提示词。
"""
from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_SYSTEM_PROMPT = """你是一位资深的美食餐饮小红书配图生图提示词工程师。用户给出一条「配图指导」方向，请按以下步骤处理：

1. 提炼核心想法：用一句话说清这张图要表达的主体、氛围和用途（封面主图 / 正文配图）
2. 结合门店信息与文案背景，把方向丰富成一条可直接交给生图模型（豆包/即梦）的中文提示词
3. 提示词必须具体可执行，覆盖：画面主体、场景环境、光线、构图、氛围情绪、色彩、质感、风格取向、画幅（3:4 竖版）
4. 面向小红书卡组封面/配图场景，突出食欲感与传播力，避免空洞形容词堆砌
5. 只输出严格 JSON（不要 markdown 代码块）：{"main_idea":"一句话核心想法","prompt":"100-200字完整提示词"}
6. 禁止出现色情、暴力、涉政、诈骗、赌博类内容"""


class ImagePromptAgentError(Exception):
    """ImagePrompt Agent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise ImagePromptAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise ImagePromptAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise ImagePromptAgentError("LLM 返回结构异常")
    return data


class StudioImagePromptAgent:
    """配图提示词丰富 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def enrich(self, direction: str, context: dict) -> dict:
        """把配图指导方向扩写为 {main_idea, prompt}。"""
        lines = ["门店信息："]
        for key, label in (
            ("category", "品类"),
            ("style", "风格"),
            ("price_range", "价格带"),
            ("topic", "主题"),
            ("shop_name", "店名"),
        ):
            val = (context or {}).get(key)
            if val:
                lines.append(f"- {label}：{val}")
        lines.append(f"配图指导方向：{direction[:500]}")
        lines.append("请按步骤处理并输出 JSON。")

        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ],
            temperature=0.85,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)

        main_idea = str(data.get("main_idea", "")).strip()
        prompt = str(data.get("prompt", "")).strip()
        if not main_idea or not prompt:
            raise ImagePromptAgentError("LLM 返回内容不完整")
        if contains_blocked(main_idea) or contains_blocked(prompt):
            raise ImagePromptAgentError("生成内容包含敏感词")
        return {
            "main_idea": main_idea[:200],
            "prompt": prompt[:1000],
        }
