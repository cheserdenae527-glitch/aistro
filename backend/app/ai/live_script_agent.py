"""LiveScriptAgent — DeepSeek 直播脚本生成。

输入：门店品类/价格带、平台、目标、优惠商品、形象人设、tone、时长。
输出：分段脚本（opening/product/promo/interaction/qa/closing）+ 合规风险提示。
约束：6 类分段齐全；总时长与 duration_min 偏差 ≤10%；敏感词过滤。
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_REQUIRED_TYPES = {"opening", "product", "promo", "interaction", "qa", "closing"}

_TYPE_LABELS = {
    "opening": "开场留人",
    "product": "产品介绍",
    "promo": "优惠逼单",
    "interaction": "互动",
    "qa": "答疑",
    "closing": "收尾",
}

_SYSTEM_PROMPT = """你是资深餐饮本地生活直播脚本策划，服务代运营团队。你的目标是写出一套「真人值守 + AI 数字人出镜」的合规直播脚本。

必须输出严格 JSON（不要 markdown 代码块），结构：
{
  "title": "脚本标题（≤20字）",
  "tone": "烟火气 | 专业 | 热情 | 治愈",
  "content": [
    {
      "type": "opening | product | promo | interaction | qa | closing",
      "title": "段标题（≤20字）",
      "text": "主播口播正文（口语化，1-3 句）",
      "duration_sec": 45,
      "cue": "画面/动作提示，用于数字人动作编排"
    }
  ],
  "compliance_risks": ["按规则自动说明的合规风险提示（没有则空数组）"]
}

规则：
1. 6 类分段必须齐全：opening（开场留人 30-60s）、product（产品介绍，招牌菜/套餐逐个讲，每个 2-4 分钟）、promo（优惠逼单 60-90s）、interaction（互动问答/点菜/抽奖）、qa（答疑：辣度/分量/配送/有效期）、closing（收尾：核销引导+关注+下场预告 60s）。product 可以有多段。
2. 总时长尽量接近用户给定 duration_min；偏差必须控制在 ±10% 内。
3. 每段必须含 cue（画面/动作提示）。
4. 合规红线：不得出现"无人直播/24小时无人直播"表述；不得使用绝对化用语（最便宜/最好吃/第一/唯一/绝对/顶级/100%/保证/承诺/根治/治愈等）；不得承诺疗效；不得引导站外交易（加微信/私下转账等）；不得出现色情、暴力、涉政、诈骗、赌博内容。
5. 数字人直播需体现"真人运营团队值守 + AI 标识"的合规语境，但不要在口播里生硬播报"AI"字样，除非需要声明。
6. 面向平台：抖音/小红书/视频号（微信）。话术要符合平台直播间口语节奏。"""


class LiveScriptAgentError(Exception):
    """LiveScriptAgent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise LiveScriptAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise LiveScriptAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise LiveScriptAgentError("LLM 返回结构异常")
    return data


def _check_generated_blocked(*values: str) -> None:
    for v in values:
        if v and contains_blocked(v):
            raise LiveScriptAgentError("生成内容包含敏感词")


class LiveScriptAgent:
    """直播脚本生成 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def generate(
        self,
        *,
        shop_name: str,
        category: str | None,
        platform: str,
        goal: str | None,
        promo_items: list[dict[str, Any]] | None,
        persona: dict[str, Any] | None,
        tone: str | None,
        duration_min: int | None,
    ) -> dict[str, Any]:
        user_msg = self._build_user_message(
            shop_name=shop_name,
            category=category,
            platform=platform,
            goal=goal,
            promo_items=promo_items or [],
            persona=persona,
            tone=tone,
            duration_min=duration_min,
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.8,
            max_tokens=4000,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)
        return self._clean_script(data, duration_min=duration_min)

    def _build_user_message(
        self,
        *,
        shop_name: str,
        category: str | None,
        platform: str,
        goal: str | None,
        promo_items: list[dict[str, Any]],
        persona: dict[str, Any] | None,
        tone: str | None,
        duration_min: int | None,
    ) -> str:
        lines = [
            "直播间信息：",
            f"- 门店：{shop_name}",
            f"- 品类：{category or '未知'}",
            f"- 平台：{platform}",
            f"- 场次目标：{goal or '未设置'}",
            f"- 总时长：{duration_min} 分钟" if duration_min else "- 总时长：未指定（按 30 分钟左右规划）",
            f"- 风格：{tone or '烟火气'}",
            "",
            "优惠商品（promo_items）：",
        ]
        if not promo_items:
            lines.append("- （无，可围绕门店招牌与到店场景展开）")
        for it in promo_items:
            lines.append(
                "- {name} | 现价={price} | 原价={original_price} | 规则={rules}".format(
                    name=it.get("name"),
                    price=it.get("price"),
                    original_price=it.get("original_price"),
                    rules=it.get("rules") or "",
                )
            )
        lines.append("")
        lines.append("数字人形象人设（persona）：")
        if persona:
            for k, v in persona.items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append("- （未关联人设，用通用亲切门店主播人设）")
        lines.append("")
        lines.append("请生成一套完整直播脚本。")
        return "\n".join(lines)

    def _clean_script(
        self, data: dict[str, Any], *, duration_min: int | None
    ) -> dict[str, Any]:
        title = str(data.get("title", "")).strip()
        tone = str(data.get("tone", "")).strip() or "烟火气"
        raw_content = data.get("content")
        if not title:
            raise LiveScriptAgentError("LLM 返回脚本缺少标题")
        if not isinstance(raw_content, list) or not raw_content:
            raise LiveScriptAgentError("LLM 返回脚本缺少分段内容")

        content: list[dict[str, Any]] = []
        seen: set[str] = set()
        for seg in raw_content:
            if not isinstance(seg, dict):
                raise LiveScriptAgentError("LLM 返回分段结构异常")
            seg_type = str(seg.get("type", ""))
            if seg_type not in _REQUIRED_TYPES:
                raise LiveScriptAgentError(f"LLM 返回无效分段类型: {seg_type}")
            seg_title = str(seg.get("title", "")).strip() or _TYPE_LABELS.get(seg_type, seg_type)
            text = str(seg.get("text", "")).strip()
            if not text:
                raise LiveScriptAgentError("LLM 返回分段缺少正文")
            try:
                duration_sec = int(seg.get("duration_sec", 0))
            except (ValueError, TypeError):
                raise LiveScriptAgentError("LLM 返回分段时长无效")
            if duration_sec < 1 or duration_sec > 3600:
                raise LiveScriptAgentError("LLM 返回分段时长无效")
            cue = str(seg.get("cue", "")).strip() or None
            seen.add(seg_type)
            content.append(
                {
                    "type": seg_type,
                    "title": seg_title[:200],
                    "text": text[:10000],
                    "duration_sec": duration_sec,
                    "cue": cue[:500] if cue else None,
                }
            )
            _check_generated_blocked(seg_title, text, cue or "")

        missing = _REQUIRED_TYPES - seen
        if missing:
            raise LiveScriptAgentError(
                f"LLM 返回脚本缺少分段类型: {','.join(sorted(missing))}"
            )

        total = sum(s["duration_sec"] for s in content)
        if duration_min:
            target = duration_min * 60
            if total < target * 0.9 or total > target * 1.1:
                raise LiveScriptAgentError(
                    f"脚本总时长 {total}s 与设定时长 {duration_min} 分钟偏差超过 10%"
                )

        risks = data.get("compliance_risks")
        compliance_risks = (
            [str(r) for r in risks if isinstance(r, str)]
            if isinstance(risks, list)
            else []
        )

        _check_generated_blocked(title)
        return {
            "title": title[:200],
            "tone": tone[:50],
            "content": content,
            "total_duration_sec": total,
            "compliance_risks": compliance_risks[:10],
        }
