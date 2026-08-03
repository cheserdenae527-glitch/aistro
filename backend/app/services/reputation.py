"""口碑管理核心状态机：差评预警双路径 + 处理流转。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.review import Review


def trigger_keyword_alert(review: "Review", keywords: list[str]) -> None:
    """同步落库时关键词命中，立即触发预警（仅新增记录调用）。"""
    review.alert_status = "triggered"
    review.alert_reason = {
        "type": "keyword",
        "keywords": keywords,
        "sentiment": None,
    }


def apply_sentiment_alert(review: "Review", sentiment: str) -> None:
    """batch-analyze 后按负面情感补充触发/合并 alert_reason。

    规则（SPEC §5.2/§5.3）：
    - ack 后完全锁定，不回跳也不改写 reason；
    - 未 ack 时 keyword -> both 合并升级；
    - 已 triggered 的记录不因 positive/neutral 撤销。
    """
    if sentiment != "negative":
        return
    if review.alert_status == "acknowledged":
        return

    reason = review.alert_reason or {}
    existing_type = reason.get("type")
    if existing_type == "keyword":
        review.alert_status = "triggered"
        review.alert_reason = {
            "type": "both",
            "keywords": reason.get("keywords") or [],
            "sentiment": "negative",
        }
    elif existing_type in ("sentiment", "both"):
        review.alert_status = "triggered"
    else:
        review.alert_status = "triggered"
        review.alert_reason = {
            "type": "sentiment",
            "keywords": [],
            "sentiment": "negative",
        }


def mark_manual_replied(review: "Review") -> None:
    """已确认回复即视为已处理：triggered 自动流转为 acknowledged。"""
    if review.alert_status == "triggered":
        review.alert_status = "acknowledged"
