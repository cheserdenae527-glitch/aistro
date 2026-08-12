"""博主分析 AI 总结 — 调 DeepSeek 生成 总结 + 优劣点 + 合作建议。"""
from __future__ import annotations

import json
import re

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


SYSTEM_PROMPT = """你是小红书餐饮博主种草分析助手，基于机器评分数据输出专业结论。输出严格 JSON（无代码块标记）：
{"summary":"一段中文总结（整体判断，150字内）","strengths":["优点1","优点2"],"weaknesses":["不足1","不足2"],"cooperate":true,"cooperate_reason":"是否建议合作及一句理由"}
规则：cooperate 用布尔值；strengths/weaknesses 各 2-4 条，基于数据而非猜测；如账号无有效评分（数据不足或被闸门拦截），summary 需明确说明并谨慎给建议。"""


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def build_prompt(result: dict) -> str:
    """从分析结果抽取紧凑信息生成 user prompt（中文）。"""
    dims = result.get("dimensions") or {}
    dim_lines = []
    for key, label in (
        ("seeding_depth", "种草深度"),
        ("verticality", "内容垂直度"),
        ("stable_output", "稳定产出"),
        ("sustained_operation", "持续经营"),
        ("growth_trend", "增长趋势"),
    ):
        d = dims.get(key) or {}
        dim_lines.append(f"{label}: {_fmt(d.get('score'))}（置信度 {_fmt(d.get('confidence'))}）")

    overall = result.get("overall") or {}
    stage = result.get("stage") or {}
    decision = result.get("decision") or {}
    cov = result.get("coverage") or {}
    gt_detail = (dims.get("growth_trend") or {}).get("detail") or {}
    insights = result.get("insights") or []
    anomalies = result.get("anomalies") or []

    lines = [
        "请基于以下小红书博主分析数据输出种草能力总结（输出 JSON）：",
        "五维评分：",
    ]
    lines.extend("  " + line for line in dim_lines)
    lines.append("")
    lines.append(f"总分/等级：{_fmt(overall.get('score'))} / {_fmt(overall.get('level'))}（{_fmt(overall.get('description'))}）")
    lines.append(f"账号阶段：{_fmt(stage.get('label'))}（置信度 {_fmt(stage.get('confidence'))}，依据 {_fmt(stage.get('evidence'))}）")
    lines.append(f"合作建议：{_fmt(decision.get('recommendation'))} — {_fmt(decision.get('summary'))}")
    if decision.get("reasons"):
        lines.append(f"理由：{'；'.join(str(r) for r in decision['reasons'])}")
    if decision.get("red_flags"):
        lines.append(f"红旗：{'；'.join(str(f.get('detail')) for f in decision['red_flags'])}")
    lines.append(f"覆盖率/可信度：{_fmt(cov.get('coverage_rate'))} / {_fmt(result.get('confidence'))}")
    if gt_detail.get("growth_rate") is not None:
        try:
            rate = float(gt_detail["growth_rate"])
        except (TypeError, ValueError):
            rate = None
        if rate is not None:
            lines.append(f"月化涨粉率：{rate * 100:.1f}%")
    if insights:
        lines.append("分析洞察：" + "；".join(str(i) for i in insights))
    lines.append("异常：" + ("；".join(f"{a.get('type')}:{a.get('detail')}" for a in anomalies) if anomalies else "无"))
    if overall.get("score") is None:
        lines.append("注意：该账号无有效评分（数据不足或被闸门拦截），请基于现有数据谨慎判断并说明。")
    return "\n".join(lines)


def _parse_json(content: str) -> dict:
    text = content.strip()
    # 剥离可能的 markdown 代码围栏
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 兜底：取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("AI 总结解析失败")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("AI 总结解析失败")
    return data


def _normalize(data: dict) -> dict:
    cooperate_raw = data.get("cooperate")
    if isinstance(cooperate_raw, str):
        cooperate = cooperate_raw.strip().lower() in ("true", "是", "建议", "1")
    else:
        cooperate = bool(cooperate_raw)
    return {
        "summary": str(data.get("summary") or ""),
        "strengths": [str(s) for s in (data.get("strengths") or []) if s],
        "weaknesses": [str(w) for w in (data.get("weaknesses") or []) if w],
        "cooperate": cooperate,
        "cooperate_reason": str(data.get("cooperate_reason") or ""),
    }


async def generate_summary(result: dict) -> dict:
    """调用 DeepSeek 生成总结；解析失败抛 ValueError。"""
    client = _get_client()
    resp = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(result)},
        ],
        temperature=0.3,
        max_tokens=600,
    )
    # 兼容 SDK 对象与测试用 dict 两类响应
    choices = getattr(resp, "choices", None) or (resp.get("choices") if isinstance(resp, dict) else None)
    if not choices:
        raise ValueError("AI 总结解析失败")
    first = choices[0]
    msg = first.get("message") if isinstance(first, dict) else first.message
    content = msg.get("content") if isinstance(msg, dict) else msg.content
    return _normalize(_parse_json(content or ""))