"""cProfile 示例：对 profile_agent 清洗逻辑做固定次数采样。"""
from __future__ import annotations

from app.ai.profile_agent import _sanitize_variants


def _raw_variant(index: int) -> dict:
    return {
        "id": str(index),
        "nickname_options": ["市井火锅", "巷子里的火锅店", "老灶台"],
        "bio": "本地人常去的火锅店",
        "avatar_prompt": "avatar",
        "bg_prompt": "bg",
        "color_scheme": {
            "primary": "#C0392B",
            "secondary": "#FDEBD0",
            "accent": "#E67E22",
            "text": "#2C3E50",
        },
    }


def main() -> None:
    raw = [_raw_variant(i) for i in range(4)]
    for _ in range(2000):
        _sanitize_variants(raw)


if __name__ == "__main__":
    main()
