"""内容工坊色板 — 移植 Guizang theme-presets（Editorial 6 套 + Swiss 4 套）。"""
from __future__ import annotations

# Editorial: paper 背景主色（QA 密度检查用），css 为 CSS 变量块。
EDITORIAL_THEMES: dict[str, dict[str, str]] = {
    "ink-classic": {
        "paper": "#f3f0e8",
        "css": """--paper:#f3f0e8;--paper-2:#ebe6da;--ink:#0a0a0b;--muted:#68625a;
--line:rgba(10,10,11,.22);--accent:#111111;--accent-soft:#d8d2c6;--ink-rgb:10,10,11;
--paper-rgb:243,240,232;--accent-rgb:17,17,17;""",
    },
    "indigo-porcelain": {
        "paper": "#f2f4f5",
        "css": """--paper:#f2f4f5;--paper-2:#e5ebef;--ink:#0a1f3d;--muted:#5f6d78;
--line:rgba(10,31,61,.20);--accent:#315d93;--accent-soft:#d7e1ec;--ink-rgb:10,31,61;
--paper-rgb:242,244,245;--accent-rgb:49,93,147;""",
    },
    "forest-ink": {
        "paper": "#f5f1e8",
        "css": """--paper:#f5f1e8;--paper-2:#e8dfcf;--ink:#16251b;--muted:#5d665d;
--line:rgba(22,37,27,.22);--accent:#2e6b4f;--accent-soft:#d4dfd2;--ink-rgb:22,37,27;
--paper-rgb:245,241,232;--accent-rgb:46,107,79;""",
    },
    "kraft-paper": {
        "paper": "#eedfc7",
        "css": """--paper:#eedfc7;--paper-2:#dfc9a8;--ink:#2a1e13;--muted:#755f49;
--line:rgba(42,30,19,.24);--accent:#9b5a2e;--accent-soft:#d5b58f;--ink-rgb:42,30,19;
--paper-rgb:238,223,199;--accent-rgb:155,90,46;""",
    },
    "dune": {
        "paper": "#f0e6d2",
        "css": """--paper:#f0e6d2;--paper-2:#ded0b7;--ink:#1f1a14;--muted:#6f6557;
--line:rgba(31,26,20,.22);--accent:#8f7650;--accent-soft:#d4c2a4;--ink-rgb:31,26,20;
--paper-rgb:240,230,210;--accent-rgb:143,118,80;""",
    },
    "midnight-ink": {
        "paper": "#0e0d0c",
        "css": """--paper:#0e0d0c;--paper-2:#1a1714;--ink:#ece2cf;--muted:#9a8c75;
--line:rgba(236,226,207,.22);--accent:#d4a04a;--accent-soft:#3a2a14;--ink-rgb:236,226,207;
--paper-rgb:14,13,12;--accent-rgb:212,160,74;""",
    },
}

SWISS_THEMES: dict[str, dict[str, str]] = {
    "ikb-blue": {
        "paper": "#fafaf8",
        "css": """--paper:#fafaf8;--ink:#0a0a0a;--grey-1:#f0f0ee;--grey-2:#d4d4d2;
--grey-3:#737373;--accent:#002FA7;--accent-on:#ffffff;""",
    },
    "lemon-yellow": {
        "paper": "#fafaf8",
        "css": """--paper:#fafaf8;--ink:#0a0a0a;--grey-1:#f0f0ee;--grey-2:#d4d4d2;
--grey-3:#737373;--accent:#FFD500;--accent-on:#0a0a0a;""",
    },
    "lemon-green": {
        "paper": "#fafaf8",
        "css": """--paper:#fafaf8;--ink:#0a0a0a;--grey-1:#f0f0ee;--grey-2:#d4d4d2;
--grey-3:#737373;--accent:#C5E803;--accent-on:#0a0a0a;""",
    },
    "safety-orange": {
        "paper": "#fafaf8",
        "css": """--paper:#fafaf8;--ink:#0a0a0a;--grey-1:#f0f0ee;--grey-2:#d4d4d2;
--grey-3:#737373;--accent:#FF6B35;--accent-on:#ffffff;""",
    },
}


def theme_css(template: str, theme: str) -> str:
    table = EDITORIAL_THEMES if template == "editorial" else SWISS_THEMES
    item = table.get(theme)
    if not item:
        raise ValueError(f"未知色板: {template}/{theme}")
    return item["css"]


def theme_paper(template: str, theme: str) -> str:
    table = EDITORIAL_THEMES if template == "editorial" else SWISS_THEMES
    item = table.get(theme)
    if not item:
        raise ValueError(f"未知色板: {template}/{theme}")
    return item["paper"]
