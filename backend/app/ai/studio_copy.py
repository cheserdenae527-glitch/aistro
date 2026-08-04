"""StudioCopyAgent — DeepSeek 小红书文案生成（Viral Writer 11 维度）。

输入品类/风格/价格带/主题/店名，输出 5 标题 + 正文 + 标签 + 配图指导。
"""
from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_SYSTEM_PROMPT = """你是资深小红书餐饮内容策划。基于 11 个内容洞见维度（核心观点、副观点、说服策略、情绪触发、金句、情感曲线、情感层次、论证多样性、视角转化、语言风格、互动钩子）为一家餐饮门店创作一篇小红书笔记文案。

小红书平台规范：
1. 标题 ≤20 字，关键词前置，可用 emoji 增加辨识度
2. 正文 300-800 字，口语化、像朋友在聊天，善用 emoji 分段
3. 标签 5-10 个
4. 结尾埋互动钩子（提问/投票/晒一晒等）

只输出严格 JSON（不要 markdown 代码块），结构：
{"titles":[{"text":"标题1","strategy":"所用策略名"},共5条],"body":"正文（300-800字）","tags":["标签1",...],"image_guide":{"cover_prompt":"封面图提示词","pages":[{"position":"第1段后","purpose":"辅助说明","prompt":"配图提示词"}]}}

要求：
- titles 恰好 5 条，每条带策略名（如 痛点共鸣/好奇心缺口/社会认同/数字具体化）
- body 严格 300-800 字
- tags 5-10 个
- image_guide.cover_prompt 描述封面主图，pages 给出 2-4 个正文配图位
- 禁止出现色情、暴力、涉政、诈骗、赌博类内容"""


class StudioAgentError(Exception):
    """Studio Agent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise StudioAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise StudioAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise StudioAgentError("LLM 返回结构异常")
    return data


def _check_generated_blocked(*values: str) -> None:
    for v in values:
        if v and contains_blocked(v):
            raise StudioAgentError("生成内容包含敏感词")


class StudioCopyAgent:
    """文案生成 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def generate(
        self,
        category: str,
        style: str,
        price_range: str,
        topic: str,
        shop_name: str,
    ) -> dict:
        user_msg = (
            "门店信息：\n"
            f"- 品类：{category}\n"
            f"- 风格：{style}\n"
            f"- 价格带：{price_range}\n"
            f"- 主题：{topic}\n"
            f"- 店名：{shop_name}\n"
            "请创作一篇小红书文案。"
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.85,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)

        titles = data.get("titles")
        body = data.get("body")
        tags = data.get("tags")
        image_guide = data.get("image_guide")

        if not isinstance(titles, list) or len(titles) != 5:
            raise StudioAgentError("LLM 返回标题数量不是 5 条")
        if not isinstance(body, str) or not (300 <= len(body) <= 800):
            raise StudioAgentError("LLM 返回正文长度不在 300-800 字")
        if not isinstance(tags, list) or not (5 <= len(tags) <= 10):
            raise StudioAgentError("LLM 返回标签数量不在 5-10 个")
        if not isinstance(image_guide, dict):
            raise StudioAgentError("LLM 返回缺少 image_guide")

        cleaned_titles: list[dict] = []
        for item in titles:
            if not isinstance(item, dict) or not item.get("text"):
                raise StudioAgentError("LLM 返回标题结构异常")
            cleaned_titles.append(
                {"text": str(item["text"])[:50], "strategy": str(item.get("strategy", ""))[:50]}
            )
            _check_generated_blocked(str(item["text"]), str(item.get("strategy", "")))

        _check_generated_blocked(body)
        for tag in tags:
            _check_generated_blocked(str(tag))

        pages = image_guide.get("pages") or []
        cleaned_pages: list[dict] = []
        for p in pages:
            if not isinstance(p, dict):
                continue
            cleaned_pages.append(
                {
                    "position": str(p.get("position", ""))[:100],
                    "purpose": str(p.get("purpose", ""))[:100],
                    "prompt": str(p.get("prompt", ""))[:2000],
                }
            )
            _check_generated_blocked(str(p.get("prompt", "")))
        cover_prompt = str(image_guide.get("cover_prompt", ""))[:2000]
        image_guide_clean = {
            "cover_prompt": cover_prompt,
            "pages": cleaned_pages[:6],
        }
        _check_generated_blocked(cover_prompt)

        return {
            "titles": cleaned_titles,
            "body": body[:5000],
            "tags": [str(t)[:30] for t in tags],
            "image_guide": image_guide_clean,
        }

