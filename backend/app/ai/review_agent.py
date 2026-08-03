"""ReviewAgent — DeepSeek 口碑分析：批量情感/关键词 + 评论回复草稿。"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

# 差评预警内置关键词（同步落库时扫描，不依赖 LLM）。
ALERT_KEYWORDS: tuple[str, ...] = (
    "卫生差",
    "不卫生",
    "有苍蝇",
    "有蟑螂",
    "头发丝",
    "分量少",
    "分量小",
    "量太少",
    "吃不饱",
    "太贵",
    "价格贵",
    "性价比低",
    "宰客",
    "刺客",
    "难吃",
    "不好吃",
    "太咸",
    "太淡",
    "没味道",
    "不新鲜",
    "难以下咽",
    "踩雷",
    "服务差",
    "态度差",
    "服务态度差",
    "服务员态度",
    "爱答不理",
    "上菜慢",
    "配送慢",
    "包装差",
    "撒了",
    "漏了",
    "等位久",
    "排队久",
    "等太久",
    "等位太久",
    "差评",
    "投诉",
    "失望",
    "再也不来",
)

_ANALYZE_SYSTEM_PROMPT = """你是一个餐饮口碑运营助手。对每条小红书笔记/评论做情感分类并提取关键词标签。

要求：
1. sentiment 只能是 positive / neutral / negative 之一
2. tags 是短关键词（如"分量少"、"价格贵"、"服务好"、"出片"），每条 0-5 个，不重复
3. 只输出纯 JSON（无代码块标记）：{"items":[{"id":"<原样返回 review id>","sentiment":"negative","tags":["分量少","价格贵"]}]}
4. 不编造内容，不输出额外解释
"""

_REPLY_SYSTEM_PROMPT = """你是一家餐饮门店的运营，为小红书评论写一条自然、真诚的回复草稿。

规则：
1. 好评：感谢认可 + 引导复购/再访
2. 差评：诚恳道歉 + 简短解释 + 可落地的补偿或改进方案，不编造事实，不承诺无法兑现的内容
3. 中性：感谢反馈 + 邀请再次光临
4. 语言口语化，符合小红书评论语境，100 字以内
5. 只输出回复正文，不要 markdown、编号、引号或解释
6. 不得出现色情、暴力、涉政、诈骗、赌博类内容
"""


class ReviewAgentError(Exception):
    """ReviewAgent 调用或解析失败。"""


@dataclass
class ReviewAnalysis:
    id: uuid.UUID
    sentiment: str
    tags: list[str]


def scan_alert_keywords(text: str | None) -> list[str]:
    """按内置关键词扫描文本，返回命中的关键词列表。"""
    if not text:
        return []
    matched: list[str] = []
    for keyword in ALERT_KEYWORDS:
        if keyword in text and keyword not in matched:
            matched.append(keyword)
    return matched


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise ReviewAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise ReviewAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise ReviewAgentError("LLM 返回结构异常")
    return data


class ReviewAgent:
    """口碑分析 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def analyze_batch(self, reviews: list) -> list[ReviewAnalysis]:
        """一次分析最多 10 条，返回情感 + 关键词标签。"""
        if not reviews:
            return []
        lines = []
        for review in reviews:
            text = (review.content or "")[:500]
            lines.append(f"{review.id}: {text}")

        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _ANALYZE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "请分析以下内容：\n" + "\n".join(lines),
                },
            ],
            temperature=0.3,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)
        items = data.get("items") or []
        if not isinstance(items, list):
            raise ReviewAgentError("LLM 返回 items 结构异常")

        valid_ids = {str(r.id) for r in reviews}
        results: list[ReviewAnalysis] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_id = str(item.get("id") or item.get("review_id") or "")
            if raw_id not in valid_ids:
                continue
            sentiment = item.get("sentiment")
            if sentiment not in ("positive", "neutral", "negative"):
                continue
            raw_tags = item.get("tags") or []
            tags = [str(t).strip() for t in raw_tags if str(t).strip()][:10]
            results.append(
                ReviewAnalysis(
                    id=uuid.UUID(raw_id),
                    sentiment=sentiment,
                    tags=tags,
                )
            )
        return results

    async def generate_reply(
        self,
        content: str,
        shop_name: str,
        category: str | None = None,
        positioning: str | None = None,
    ) -> str:
        """生成 1 条评论回复草稿（好评/差评/中性模板 + 门店信息）。"""
        shop_info = f"- 门店：{shop_name or '本店'}"
        if category:
            shop_info += f"\n- 品类：{category}"
        if positioning:
            shop_info += f"\n- 定位：{positioning}"
        user_msg = (
            f"{shop_info}\n- 评论内容：{content[:500]}\n"
            "请生成一条合适的回复草稿。"
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        draft = (response.choices[0].message.content or "").strip()
        draft = _JSON_FENCE_RE.sub("", draft).strip()
        if contains_blocked(draft):
            raise ReviewAgentError("生成内容包含敏感词")
        return draft[:2000]
