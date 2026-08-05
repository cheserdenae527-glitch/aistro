"""DealCopyAgent — DeepSeek 平台差异化文案生成（抖音/美团/小红书）。"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_PLATFORM_GUIDES = {
    "douyin": (
        "抖音：标题用「数字+场景+情绪」制造一眼看懂的值，卖点突出强对比与货架感；"
        "cover_prompt 按视频/直播货架封面写，强对比、大字报、价格醒目。"
    ),
    "meituan": (
        "美团/点评：标题品类关键词前置，卖点突出价格带与评分；"
        "cover_prompt 按干净实拍封面写，突出套餐包含明细。"
    ),
    "xiaohongshu": (
        "小红书：标题突出玩法/仪式感，卖点突出打卡与场景种草；"
        "cover_prompt 按 3:4 种草风写，突出人物/环境氛围。"
    ),
}

_SYSTEM_PROMPT = """你是资深餐饮平台运营文案专家。针对同一套团购套餐，为指定平台输出差异化文案。

输出严格 JSON（不要 markdown 代码块），结构：
{
  "title": "该平台标题（≤20字，按平台策略）",
  "selling_points": ["卖点1", "卖点2", "卖点3"],
  "rules": "使用规则/适用说明（1-2句）",
  "cover_prompt": "该平台封面生图提示词（详细描述构图/元素/文字/风格）"
}

平台策略：{platform_guide}

要求：
- selling_points 3-6 条，每条突出一个可感知价值
- 禁止出现色情、暴力、涉政、诈骗、赌博类内容"""


class DealCopyAgentError(Exception):
    """DealCopyAgent 调用或解析失败。"""


def build_system_prompt(platform: str) -> str:
    """构造平台差异化系统提示词。

    注意：prompt 内含 JSON 大括号，不能用 str.format（会把 {..} 当占位符），用 replace。
    """
    guide = _PLATFORM_GUIDES.get(platform, _PLATFORM_GUIDES["douyin"])
    return _SYSTEM_PROMPT.replace("{platform_guide}", guide)


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise DealCopyAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise DealCopyAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise DealCopyAgentError("LLM 返回结构异常")
    return data


def _check_generated_blocked(*values: str) -> None:
    for v in values:
        if v and contains_blocked(v):
            raise DealCopyAgentError("生成内容包含敏感词")


class DealCopyAgent:
    """平台文案生成 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def generate(
        self,
        *,
        platform: str,
        shop_name: str,
        shop_category: str | None,
        scheme: dict[str, Any],
    ) -> dict[str, Any]:
        system_prompt = build_system_prompt(platform)

        items_text = "\n".join(
            "- {name} × {qty}（售价 {sale}，成本 {cost}）".format(
                name=it.get("name"),
                qty=it.get("qty"),
                sale=it.get("sale_price"),
                cost=it.get("cost_price"),
            )
            for it in (scheme.get("items") or [])
        )
        user_msg = (
            "门店信息：\n"
            f"- 店名：{shop_name}\n"
            f"- 品类：{shop_category or '未知'}\n\n"
            "套餐方案：\n"
            f"- 类型：{scheme.get('scheme_type')}\n"
            f"- 标题：{scheme.get('title')}\n"
            f"- 描述：{scheme.get('description') or ''}\n"
            f"- 原价：{scheme.get('original_price')}，团购价：{scheme.get('deal_price')}\n"
            "组合明细：\n"
            f"{items_text or '（无）'}\n"
            f"请为【{platform}】平台生成差异化文案。"
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.85,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)

        title = str(data.get("title", "")).strip()
        selling_points = data.get("selling_points")
        rules = str(data.get("rules", "")).strip()
        cover_prompt = str(data.get("cover_prompt", "")).strip()

        if not title:
            raise DealCopyAgentError("LLM 返回标题为空")
        if not isinstance(selling_points, list) or len(selling_points) < 1:
            raise DealCopyAgentError("LLM 返回卖点数量不足")
        if not cover_prompt:
            raise DealCopyAgentError("LLM 返回封面提示词为空")

        cleaned_points = [str(x).strip()[:500] for x in selling_points if str(x).strip()]
        if not cleaned_points:
            raise DealCopyAgentError("LLM 返回卖点数量不足")
        _check_generated_blocked(
            title, rules, cover_prompt, *cleaned_points
        )

        return {
            "title": title[:200],
            "selling_points": cleaned_points[:8],
            "rules": rules[:2000] or None,
            "cover_prompt": cover_prompt[:2000],
        }


