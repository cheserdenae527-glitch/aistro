"""StudioPaginateAgent — DeepSeek 正文分页：正文 → page_specs。"""
from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_SYSTEM_PROMPT = """你是小红书卡组排版策划。把一篇小红书笔记正文拆成 N 页竖版卡片内容（1080x1440，3:4）。

规则：
1. 每页只讲 1 个观点
2. 标题 12-30 字（封面页为抓眼大标题钩子，可放宽到 8-20 字）
3. 每页要点 2-4 条（封面页要点条 3-5 条）
4. image_index 表示该页使用的素材图序号（从 0 开始），没有合适配图用 null
5. 第 1 页是封面页：大标题钩子 + 3-5 个要点条 + image_index=0（有图时）
6. 正文信息不能丢失，观点要覆盖完整

只输出严格 JSON（不要 markdown 代码块）：
{"page_specs":[{"title":"标题","bullets":["要点1","要点2"],"image_index":0}]}

要求：page_specs 恰好 N 条；标题 12-30 字（封面除外）；每页要点 2-4 条；image_index 在 0..M-1 之间或 null。禁止出现色情、暴力、涉政、诈骗、赌博类内容。"""


class StudioPaginateError(Exception):
    """分页 Agent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise StudioPaginateError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise StudioPaginateError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise StudioPaginateError("LLM 返回结构异常")
    return data


class StudioPaginateAgent:
    """分页 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def paginate(self, body: str, page_count: int, image_count: int) -> list[dict]:
        if not (4 <= page_count <= 8):
            raise StudioPaginateError("page_count 必须在 4-8")
        user_msg = (
            f"正文：\n{body[:5000]}\n\n"
            f"请把正文拆成 {page_count} 页卡组。素材图共 {image_count} 张（无图则 image_index 用 null）。"
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)
        specs = data.get("page_specs")
        if not isinstance(specs, list) or len(specs) != page_count:
            raise StudioPaginateError(
                f"LLM 返回页数 {len(specs) if isinstance(specs, list) else '异常'} 不等于 {page_count}"
            )

        cleaned: list[dict] = []
        for i, spec in enumerate(specs):
            if not isinstance(spec, dict):
                raise StudioPaginateError("LLM 返回分页结构异常")
            title = str(spec.get("title", "")).strip()
            bullets = spec.get("bullets")
            if not title:
                raise StudioPaginateError("LLM 返回页标题为空")
            # 标题长度：封面截断到 20 字，内容页截断到 30 字；过短不阻断（视觉质量由 QA 把关）
            if i == 0:
                title = title[:20]
            else:
                title = title[:30]
            if not isinstance(bullets, list) or not (1 <= len(bullets) <= 5):
                raise StudioPaginateError(f"第 {i + 1} 页要点数量应为 2-4 条")
            image_index = spec.get("image_index")
            if image_index is not None:
                try:
                    image_index = int(image_index)
                except (TypeError, ValueError):
                    image_index = None
                # 越界时降级为纯文字页（无图），避免整个卡组失败
                if image_index is not None:
                    if image_count and not (0 <= image_index < image_count):
                        image_index = None
                    elif not image_count:
                        image_index = None
            for b in bullets:
                if contains_blocked(str(b)):
                    raise StudioPaginateError("生成内容包含敏感词")
            if contains_blocked(title):
                raise StudioPaginateError("生成内容包含敏感词")
            cleaned.append(
                {
                    "title": title[:30],
                    "bullets": [str(b).strip()[:80] for b in bullets],
                    "image_index": image_index,
                }
            )
        return cleaned
