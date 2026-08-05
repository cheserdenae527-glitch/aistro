"""团购工坊业务逻辑 — 毛利估算（SPEC-DEALS §4 口径）。"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

# 平台佣金行业均值默认值（MVP：不支持门店级实际费率覆盖，人工编辑可改）
# 口径与 SPEC-DEALS §4 / §5 一致，后续可改为配置项。
DEFAULT_COMMISSION_RATES: dict[str, float] = {
    "douyin": 0.06,
    "meituan": 0.08,
    "xiaohongshu": 0.05,
}


def platform_commission_rate(platform: str) -> float:
    """按项目主平台取默认佣金率，未知平台回落抖音默认值。"""
    return DEFAULT_COMMISSION_RATES.get(platform, DEFAULT_COMMISSION_RATES["douyin"])


def compute_margins(
    deal_price: Decimal | float,
    cost_estimate: Decimal | float,
    commission_rate: float,
) -> dict[str, float]:
    """按 SPEC 公式计算毛利：
    gross_margin = (deal_price - 组合成本) / deal_price
    net_margin = (deal_price × (1 - commission) - 组合成本) / deal_price
    """
    deal_f = float(deal_price)
    cost_f = float(cost_estimate)
    if deal_f <= 0:
        raise ValueError("deal_price 必须为正")
    gross = (deal_f - cost_f) / deal_f
    net = (deal_f * (1 - commission_rate) - cost_f) / deal_f
    return {
        "gross_margin": round(gross, 4),
        "platform_commission_rate": commission_rate,
        "net_margin": round(net, 4),
    }


def build_margin_estimate(
    deal_price: Decimal,
    cost_estimate: Decimal,
    commission_rate: float,
    *,
    estimated: bool = False,
    scheme_type: str = "",
) -> dict[str, Any]:
    """生成 margin_estimate 完整结构（含 note 警示）。"""
    margins = compute_margins(deal_price, cost_estimate, commission_rate)
    notes: list[str] = []
    if estimated:
        notes.append("含 AI 估算成本，请按实际成本校正")
    if scheme_type == "hook":
        notes.append("引流款核心是拉新到店，毛利允许偏低")
    if margins["net_margin"] < 0:
        notes.append("净毛利为负：请重新评估组合/定价，确认后再上线")
    return {
        **margins,
        "note": "；".join(notes),
    }
