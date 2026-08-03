"""预设色系方案 — 8 套，供 AI 生成和前端色板面板使用。"""
from __future__ import annotations

from app.schemas.profile import ColorSchemePreset

COLOR_PRESETS: list[ColorSchemePreset] = [
    ColorSchemePreset(
        name="暖冬橘",
        primary="#E8793A",
        secondary="#FFF3EC",
        accent="#D4520A",
        text="#2D1A0A",
        description="火锅/中式正餐",
    ),
    ColorSchemePreset(
        name="森系绿",
        primary="#4A8C5C",
        secondary="#F0F7F1",
        accent="#2D6A3F",
        text="#1A2D1F",
        description="轻食/沙拉/素食",
    ),
    ColorSchemePreset(
        name="莫兰迪",
        primary="#9B8E8A",
        secondary="#F5F2F0",
        accent="#7A6E6A",
        text="#3A3330",
        description="甜品/咖啡",
    ),
    ColorSchemePreset(
        name="日系奶油",
        primary="#E8C37A",
        secondary="#FFFBF0",
        accent="#C49A3C",
        text="#4A3A1A",
        description="烘焙/面包/Brunch",
    ),
    ColorSchemePreset(
        name="高级灰",
        primary="#6B6B6B",
        secondary="#F7F7F7",
        accent="#4A4A4A",
        text="#1A1A1A",
        description="高端餐饮/西餐",
    ),
    ColorSchemePreset(
        name="江湖红",
        primary="#C93828",
        secondary="#FFF0EE",
        accent="#A82015",
        text="#2A0A08",
        description="川菜/湘菜/江湖菜",
    ),
    ColorSchemePreset(
        name="清凉蓝",
        primary="#5B8FB8",
        secondary="#F0F6FA",
        accent="#3D6D8E",
        text="#1A2A38",
        description="日料/海鲜",
    ),
    ColorSchemePreset(
        name="深夜紫",
        primary="#7B5EA7",
        secondary="#F5F0FA",
        accent="#5E3F89",
        text="#201838",
        description="酒吧/居酒屋",
    ),
]

COLOR_PRESETS_BY_NAME: dict[str, ColorSchemePreset] = {
    p.name: p for p in COLOR_PRESETS
}
