"""pytest-benchmark 微基准示例，只依赖 profile_agent 的纯函数。"""
from __future__ import annotations

from app.ai.profile_agent import _sanitize_variants


def _raw_variant(index: int) -> dict:
    return {
        "id": str(index),
        "nickname_options": ["市井火锅", "巷子里的火锅店", "老灶台"]
        if index % 2
        else ["市井火锅", "刷单推广"],
        "bio": "本地人常去的火锅店" if index % 3 else "加微信刷单赚钱",
        "avatar_prompt": "avatar",
        "bg_prompt": "bg",
        "color_scheme": {
            "primary": "#C0392B",
            "secondary": "#FDEBD0",
            "accent": "#E67E22",
            "text": "#2C3E50",
        },
    }


def test_sanitize_variants_benchmark(benchmark):
    raw = [_raw_variant(i) for i in range(4)]
    result = benchmark(_sanitize_variants, raw)
    assert len(result) == 4
