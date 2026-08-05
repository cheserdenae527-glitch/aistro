"""敏感词过滤 — 黑名单覆盖：色情、暴力、涉政、诈骗、赌博。

所有文本内容（昵称/简介/prompt）在入库/生成前统一经过此模块。
"""
from __future__ import annotations

import re

# 黑名单关键词（可后续扩展为外部配置/数据库驱动）
_BLACKLIST: tuple[str, ...] = (
    # 色情
    "裸",
    "成人",
    "色情",
    "约炮",
    "嫖",
    "妓",
    "性爱",
    # 暴力
    "杀人",
    "自杀",
    "恐怖",
    "爆炸",
    # 涉政
    "习近平",
    "江泽民",
    "胡锦涛",
    "温家宝",
    "李克强",
    "共产党",
    "国民党",
    "六四",
    "法轮功",
    "天安门",
    "台独",
    "藏独",
    "疆独",
    "港独",
    "习近平",
    "包子",
    "维尼",
    # 诈骗
    "刷单",
    "赌博",
    "赌场",
    "博彩",
    "彩票预测",
    "日赚",
    "兼职打字",
    # 赌博
    "百家乐",
    "澳门赌场",
    "六合彩",
)

_compiled: re.Pattern[str] | None = None


def _get_pattern() -> re.Pattern[str]:
    global _compiled
    if _compiled is None:
        escaped = (re.escape(kw) for kw in _BLACKLIST)
        _compiled = re.compile("|".join(escaped), re.IGNORECASE)
    return _compiled


def blacklist() -> tuple[str, ...]:
    """返回内置敏感词库（供直播工坊导出开播包 wordlist 等场景复用）。"""
    return _BLACKLIST


def contains_blocked(text: str) -> bool:
    """检查文本是否含敏感词。"""
    if not text:
        return False
    return bool(_get_pattern().search(text))


def filter_text(text: str, replacement: str = "[内容待审核]") -> tuple[str, bool]:
    """过滤敏感词并返回 (处理后的文本, 是否被标记)。

    - 标记场景（bio）：整段替换为 replacement，返回 (replacement, True)
    - 拒绝场景（nickname/prompt）：返回 (原文本, True)，由调用方决定 400 还是剔除
    """
    if not text:
        return text, False
    if _get_pattern().search(text):
        return replacement, True
    return text, False

