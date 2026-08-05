"""LiveCompliance — 直播脚本合规自检（规则引擎）。

检查项（SPEC §5.4，脚本定稿阶段）：
1. AI 标识文案存在（live_projects.ai_label_text 非空）
2. 人设无绝对化/承诺（校验 live_scripts.persona_snapshot 快照，不实时查形象）
3. 内容无敏感词（内置词库 + 红线话术如"无人直播"）
4. 无站外交易引导

返回 {"pass": bool, "items": [{"key", "ok", "detail"}]}。
"""
from __future__ import annotations

from typing import Any

from app.core.sensitive_filter import contains_blocked

# 红线话术：不得宣传"无人直播/24小时无人直播"
_RED_LINE_PHRASES: tuple[str, ...] = (
    "无人直播",
    "24小时无人直播",
    "24 小时无人直播",
    "全天无人直播",
    "不用人管",
)

# 绝对化 / 承诺 / 医疗效果类用语（用于人设与内容审核）
_ABSOLUTE_PHRASES: tuple[str, ...] = (
    "最便宜",
    "最好吃",
    "最好",
    "最正宗",
    "第一",
    "唯一",
    "绝对",
    "顶级",
    "国家级",
    "极致",
    "全网",
    "100%",
    "百分百",
    "保证",
    "承诺",
    "根治",
    "治愈",
    "疗效",
    "药到病除",
    "永不复发",
    "包治",
    "无副作用",
    "纯天然",
    "零添加",
)

# 站外交易引导
_OFF_PLATFORM_PHRASES: tuple[str, ...] = (
    "加微信",
    "加我微信",
    "微信转账",
    "微信付款",
    "加v",
    "加V",
    "vx",
    "VX",
    "私信转账",
    "私下交易",
    "支付宝转账",
    "线下转账",
    "站外交易",
    "绕过平台",
    "转账给我",
)


# 否定前缀：命中前带这些字视为"不承诺/不保证/无副作用"类否定表述，不算违规
_NEGATION_PREFIXES = ("不", "无", "非", "别", "没", "免")


def _find_hit(text: str, phrases: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for phrase in phrases:
        p = phrase.lower()
        idx = lowered.find(p)
        while idx != -1:
            # 命中词前 4 字窗口内出现否定前缀（不/无/非/别/没/免）视为否定表述
            window = lowered[max(0, idx - 4):idx]
            if not any(c in window for c in _NEGATION_PREFIXES):
                return phrase
            idx = lowered.find(p, idx + 1)
    return None


def _iter_texts(value: Any):
    """递归收集 dict/list/str 中的字符串。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_texts(item)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _iter_texts(k)
            yield from _iter_texts(v)


class LiveCompliance:
    """规则引擎合规自检（纯本地，不调用 LLM）。"""

    @staticmethod
    def check(
        *,
        ai_label_text: str | None,
        persona_snapshot: dict[str, Any] | None,
        content: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []

        # 1. AI 标识文案存在
        ai_ok = bool(ai_label_text and ai_label_text.strip())
        items.append(
            {
                "key": "ai_label",
                "ok": ai_ok,
                "detail": "AI 标识文案已配置" if ai_ok else "未配置 AI 标识文案（live_projects.ai_label_text 为空）",
            }
        )

        # 2. 人设无绝对化/承诺（基于快照）
        if not persona_snapshot:
            items.append(
                {
                    "key": "persona",
                    "ok": True,
                    "detail": "未关联形象人设（persona_snapshot 为空），跳过人设审核",
                }
            )
        else:
            persona_text = " ".join(_iter_texts(persona_snapshot))
            hit = _find_hit(persona_text, _ABSOLUTE_PHRASES)
            if hit:
                items.append(
                    {
                        "key": "persona",
                        "ok": False,
                        "detail": f"人设含绝对化/承诺用语：{hit}",
                    }
                )
            else:
                items.append({"key": "persona", "ok": True, "detail": "人设无绝对化/承诺用语"})

        # 3. 内容无敏感词 / 红线话术
        content_text = " ".join(_iter_texts(content or []))
        if contains_blocked(content_text):
            items.append(
                {"key": "sensitive", "ok": False, "detail": "脚本内容命中敏感词"}
            )
        else:
            red_hit = _find_hit(content_text, _RED_LINE_PHRASES)
            if red_hit:
                items.append(
                    {
                        "key": "sensitive",
                        "ok": False,
                        "detail": f"脚本内容含红线话术：{red_hit}",
                    }
                )
            else:
                items.append({"key": "sensitive", "ok": True, "detail": "脚本内容无敏感词/红线话术"})

        # 4. 无站外交易引导
        off_hit = _find_hit(content_text, _OFF_PLATFORM_PHRASES)
        if off_hit:
            items.append(
                {
                    "key": "off_platform",
                    "ok": False,
                    "detail": f"脚本含站外交易引导：{off_hit}",
                }
            )
        else:
            items.append({"key": "off_platform", "ok": True, "detail": "无站外交易引导"})

        return {"pass": all(i["ok"] for i in items), "items": items}


# 默认开播包 wordlist：内置敏感词库 + 红线话术 + 站外交易引导词
def default_wordlist() -> list[str]:
    from app.core.sensitive_filter import blacklist

    words = list(blacklist())
    for phrase in (*_RED_LINE_PHRASES, *_OFF_PLATFORM_PHRASES):
        if phrase not in words:
            words.append(phrase)
    return words



