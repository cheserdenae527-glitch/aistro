"""LiveReviewAgent — DeepSeek 场次复盘报告生成。"""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_SYSTEM_PROMPT = """你是餐饮直播间数据分析师。根据场次复盘数据（手动录入）与脚本概要，输出一份复盘报告。

输出要求：
1. 纯文本（不要 JSON/markdown 代码块），300-600 字。
2. 结构：数据解读（峰值/停留/互动/订单/GMV/核销）→ 异常点 → 下场改进建议（3 条以内）。
3. 客观、口语化、可执行；不编造未提供的数据；缺失数据标注"未录入"。
4. 不含色情、暴力、涉政、诈骗、赌博内容。"""


class LiveReviewAgentError(Exception):
    """LiveReviewAgent 调用或解析失败。"""


class LiveReviewAgent:
    """场次复盘 Agent。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def review(
        self,
        *,
        metrics: dict[str, Any],
        script_summary: str | None,
    ) -> str:
        user_msg = self._build_user_message(metrics=metrics, script_summary=script_summary)
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.6,
            max_tokens=1500,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raise LiveReviewAgentError("LLM 返回空复盘报告")
        if contains_blocked(raw):
            raise LiveReviewAgentError("生成内容包含敏感词")
        # 去掉可能出现的 markdown 代码块围栏
        raw = raw.replace("```markdown", "").replace("```json", "").replace("```", "")
        return raw.strip()

    def _build_user_message(
        self,
        *,
        metrics: dict[str, Any],
        script_summary: str | None,
    ) -> str:
        lines = ["复盘数据（手动录入）："]
        if not metrics:
            lines.append("- （空）")
        for k, v in metrics.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("脚本概要：")
        lines.append(script_summary or "（未关联脚本）")
        lines.append("")
        lines.append("请输出复盘报告。")
        return "\n".join(lines)
