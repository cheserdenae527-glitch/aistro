"""DealAgent — DeepSeek 团购套餐方案生成。

输入：门店品类/名称/主平台/价格带 + 菜品清单 + 竞品套餐参考。
输出：3 款套餐方案（hook 引流款 / profit 利润款 / scenario 场景款），
每款含组合（item_id + qty + 估算成本）、标题、描述、原价/团购价。
成本口径：菜品有真实成本用真实值；缺失时由 AI 按品类行业均值估算。
"""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```")

_SYSTEM_PROMPT = """你是资深餐饮团购套餐设计专家，服务代运营团队。你的目标是：套餐不是打折，而是「决策成本最小化 + 组合利润最大化 + 引流到店」。

你必须输出严格 JSON（不要 markdown 代码块），结构：
{
  "schemes": [
    {
      "scheme_type": "hook | profit | scenario",
      "title": "套餐标题（≤20字）",
      "description": "组合卖点/适用说明（1-3句）",
      "original_price": 68.0,
      "deal_price": 39.9,
      "items": [
        {"item_id": "菜品的真实id", "qty": 1, "cost_price": 20.0}
      ]
    }
  ]
}

规则：
1. 恰好 3 款：hook（引流款，价格低、核销快、毛利可低但别亏）、profit（利润款，主战场，客单价锚定商圈中位）、scenario（场景款，工作日午餐/周末专享/宵夜等补空位）。
2. 每款至少包含 1 道招牌菜（is_signature=true）+ 1 道高毛利菜（is_high_margin=true）；若输入数据不足，尽量逼近并在 description 标注。
3. items 只能引用输入菜品列表中的 id；qty 为数量（≥1）。
4. cost_price：若该菜品输入中已有真实成本（cost 非空），必须原样带出；若 cost 为空，按该品类行业均值估算一个成本并带出（后续系统会标记为估算）。
5. original_price 为组合原价锚定（可约等于单品售价之和），deal_price 必须 < original_price，且尽量让净毛利 ≥ 0。
6. 禁止出现色情、暴力、涉政、诈骗、赌博类内容。"""


class DealAgentError(Exception):
    """DealAgent 调用或解析失败。"""


def _parse_json(raw: str) -> dict:
    clean = _JSON_FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            raise DealAgentError("LLM 返回无法解析的 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise DealAgentError("LLM 返回无法解析的 JSON")
    if not isinstance(data, dict):
        raise DealAgentError("LLM 返回结构异常")
    return data


def _check_generated_blocked(*values: str) -> None:
    for v in values:
        if v and contains_blocked(v):
            raise DealAgentError("生成内容包含敏感词")


def _to_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DealAgentError(f"LLM 返回 {field} 无效")


class DealAgent:
    """套餐方案生成 Agent，复用 DeepSeek 客户端配置。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    async def generate_schemes(
        self,
        *,
        shop_name: str,
        category: str | None,
        platform: str,
        price_band: str | None,
        items: list[dict[str, Any]],
        competitor_deals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        user_msg = self._build_user_message(
            shop_name=shop_name,
            category=category,
            platform=platform,
            price_band=price_band,
            items=items,
            competitor_deals=competitor_deals,
        )
        response = await self._client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.8,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content or "{}"
        data = _parse_json(raw)

        schemes = data.get("schemes")
        if not isinstance(schemes, list) or len(schemes) != 3:
            raise DealAgentError("LLM 返回方案数量不是 3 款")
        types = {s.get("scheme_type") for s in schemes if isinstance(s, dict)}
        if types != {"hook", "profit", "scenario"}:
            raise DealAgentError("LLM 返回三款方案类型不完整")

        return [self._clean_scheme(s) for s in schemes]

    def _build_user_message(
        self,
        *,
        shop_name: str,
        category: str | None,
        platform: str,
        price_band: str | None,
        items: list[dict[str, Any]],
        competitor_deals: list[dict[str, Any]],
    ) -> str:
        lines = [
            "门店信息：",
            f"- 店名：{shop_name}",
            f"- 品类：{category or '未知'}",
            f"- 主平台：{platform}",
            f"- 价格带：{price_band or '未设置'}",
            "",
            "菜品清单（id/名称/品类/成本/售价/招牌/高毛利）：",
        ]
        for it in items:
            lines.append(
                "- {id} | {name} | {category} | 成本={cost} | 售价={sale} | "
                "招牌={sig} | 高毛利={hm}".format(
                    id=it.get("id"),
                    name=it.get("name"),
                    category=it.get("category"),
                    cost=it.get("cost_price"),
                    sale=it.get("sale_price"),
                    sig=it.get("is_signature"),
                    hm=it.get("is_high_margin"),
                )
            )
        lines.append("")
        lines.append("竞品套餐参考（名称/价格/内容/备注）：")
        if not competitor_deals:
            lines.append("- （无）")
        for cd in competitor_deals:
            lines.append(
                "- {name} | {price} | {summary} | {note}".format(
                    name=cd.get("name"),
                    price=cd.get("price"),
                    summary=cd.get("items_summary"),
                    note=cd.get("note") or "",
                )
            )
        lines.append("")
        lines.append("请生成 3 款套餐方案。")
        return "\n".join(lines)

    def _clean_scheme(self, s: Any) -> dict[str, Any]:
        if not isinstance(s, dict):
            raise DealAgentError("LLM 返回方案结构异常")
        scheme_type = str(s.get("scheme_type", ""))
        title = str(s.get("title", "")).strip()
        description = str(s.get("description", "")).strip()
        raw_items = s.get("items")
        if scheme_type not in ("hook", "profit", "scenario"):
            raise DealAgentError("LLM 返回方案类型无效")
        if not title:
            raise DealAgentError("LLM 返回方案缺少标题")
        if not isinstance(raw_items, list) or len(raw_items) < 1:
            raise DealAgentError("LLM 返回方案缺少菜品组合")

        items: list[dict[str, Any]] = []
        for it in raw_items:
            if not isinstance(it, dict):
                raise DealAgentError("LLM 返回方案菜品结构异常")
            try:
                item_id = str(uuid.UUID(str(it.get("item_id"))))
            except ValueError:
                raise DealAgentError("LLM 返回菜品 item_id 无效")
            try:
                qty = int(it.get("qty", 1))
            except (ValueError, TypeError):
                raise DealAgentError("LLM 返回菜品数量无效")
            if qty < 1 or qty > 99:
                raise DealAgentError("LLM 返回菜品数量无效")
            cost = it.get("cost_price")
            items.append(
                {
                    "item_id": item_id,
                    "qty": qty,
                    "cost_price": (
                        _to_decimal(cost, "菜品成本") if cost is not None else None
                    ),
                }
            )

        original_price = _to_decimal(s.get("original_price"), "原价")
        deal_price = _to_decimal(s.get("deal_price"), "团购价")
        if original_price <= 0 or deal_price <= 0:
            raise DealAgentError("LLM 返回价格无效")
        _check_generated_blocked(title, description)

        return {
            "scheme_type": scheme_type,
            "title": title[:200],
            "description": description[:5000] or None,
            "items": items,
            "original_price": original_price,
            "deal_price": deal_price,
        }
