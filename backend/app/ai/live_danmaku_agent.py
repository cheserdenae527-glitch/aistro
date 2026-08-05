"""LiveDanmakuAgent — DeepSeek 弹幕互动规则生成。

输入：人设 + 定稿脚本 + 平台。
输出：reply_rules（餐饮常见弹幕场景）、sensitive_words 补充、escalate_topics。
约束：命中 escalate_topics 的规则 mode 强制 manual；auto 仅限引擎支持平台（B站等）；
敏感词过滤。
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

# 引擎支持弹幕自动回复的平台（digital-human-livestream 原生 B站）；其余一律 manual。
_AUTO_SUPPORTED_PLATFORMS = {"bilibili"}


class LiveDanmakuAgentError(Exception):
    """LiveDanmakuAgent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise LiveDanmakuAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise LiveDanmakuAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise LiveDanmakuAgentError("LLM 返回结构异常")
    return data


def _check_generated_blocked(*values: str) -> None:
    for v in values:
        if v and contains_blocked(v):
            raise LiveDanmakuAgentError("生成内容包含敏感词")


class LiveDanmakuAgent:
    """弹幕互动规则生成 Agent。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def generate(
        self,
        *,
        platform: str,
        persona: dict[str, Any] | None,
        script: dict[str, Any] | None,
    ) -> dict[str, Any]:
        user_msg = self._build_user_message(platform=platform, persona=persona, script=script)
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)
        return self._clean_config(data, platform=platform)

    def _system_prompt(self) -> str:
        return """你是餐饮直播间弹幕互动规则设计师。根据人设与定稿脚本，生成数字人直播间的弹幕回复规则。

必须输出严格 JSON（不要 markdown 代码块），结构：
{
  "persona": {"name": "店长小雅", "personality": "...", "style": "...", "knowledge_scope": "...", "forbidden_topics": ["政治", "宗教"]},
  "reply_rules": [
    {"trigger": "优惠", "reply": "今日套餐 9.9 元起，点小黄车就能下单", "mode": "manual"}
  ],
  "sensitive_words": ["补充的敏感词1"],
  "escalate_topics": ["投诉", "价格争议", "食品安全", "优惠领取"]
}

规则：
1. reply_rules 覆盖常见餐饮弹幕场景：优惠怎么领、辣度、分量、排队、有效期、地址、配送、招牌菜推荐、缺货/售罄、主播是谁等，8-15 条。
2. trigger 是观众弹幕触发词/短语（可含通配意），reply 是该触发下主播应回复的话术（口语化、合规）。
3. mode 填 "manual"（人工粘贴）或 "auto"（仅平台支持自动回复时）；默认 manual。
4. escalate_topics：投诉、价格争议、食品安全、优惠领取失败等必须转真人的话题。
5. persona 保持输入人设，可微调得更适合弹幕互动。
6. sensitive_words：补充平台/行业敏感词（如诱导站外交易、绝对化用语、医疗承诺等）。
7. 红线：不出现"无人直播/24小时无人直播"；不引导加微信/私下转账；不含色情、暴力、涉政、诈骗、赌博内容。"""

    def _build_user_message(
        self,
        *,
        platform: str,
        persona: dict[str, Any] | None,
        script: dict[str, Any] | None,
    ) -> str:
        lines = [
            f"平台：{platform}",
            "人设：",
        ]
        if persona:
            for k, v in persona.items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append("- （未提供，请给通用亲切门店主播人设）")
        lines.append("")
        lines.append("定稿脚本概要：")
        if script:
            lines.append(f"标题：{script.get('title', '')}")
            content = script.get("content") or []
            for seg in content:
                if isinstance(seg, dict):
                    lines.append(
                        f"- [{seg.get('type')}] {seg.get('title')}：{seg.get('text', '')[:120]}"
                    )
        else:
            lines.append("- （无）")
        lines.append("")
        lines.append("请生成弹幕互动规则。")
        return "\n".join(lines)

    def _clean_config(self, data: dict[str, Any], *, platform: str) -> dict[str, Any]:
        persona = data.get("persona")
        if not isinstance(persona, dict):
            persona = None
        if persona is not None:
            _check_generated_blocked(*[str(v) for v in persona.values()])

        raw_rules = data.get("reply_rules")
        if not isinstance(raw_rules, list):
            raise LiveDanmakuAgentError("LLM 返回回复规则结构异常")

        raw_escalate = data.get("escalate_topics")
        escalate_topics = (
            [str(t).strip() for t in raw_escalate if str(t).strip()]
            if isinstance(raw_escalate, list)
            else []
        )
        _check_generated_blocked(*escalate_topics)

        auto_ok = platform in _AUTO_SUPPORTED_PLATFORMS
        reply_rules: list[dict[str, Any]] = []
        for rule in raw_rules:
            if not isinstance(rule, dict):
                raise LiveDanmakuAgentError("LLM 返回回复规则结构异常")
            trigger = str(rule.get("trigger", "")).strip()
            reply = str(rule.get("reply", "")).strip()
            if not trigger or not reply:
                raise LiveDanmakuAgentError("LLM 返回回复规则缺少触发词或回复")
            mode = str(rule.get("mode", "manual")).strip()
            if mode not in ("auto", "manual"):
                mode = "manual"
            if not auto_ok:
                mode = "manual"
            # 命中 escalate_topics 的规则强制转人工
            if any(topic and topic in trigger for topic in escalate_topics):
                mode = "manual"
            _check_generated_blocked(trigger, reply)
            reply_rules.append({"trigger": trigger[:200], "reply": reply[:2000], "mode": mode})

        if not reply_rules:
            raise LiveDanmakuAgentError("LLM 返回回复规则为空")

        raw_words = data.get("sensitive_words")
        sensitive_words = (
            [str(w).strip() for w in raw_words if str(w).strip()]
            if isinstance(raw_words, list)
            else []
        )
        _check_generated_blocked(*sensitive_words)

        return {
            "persona": persona,
            "reply_rules": reply_rules[:50],
            "sensitive_words": sensitive_words[:100],
            "escalate_topics": escalate_topics[:30],
        }
