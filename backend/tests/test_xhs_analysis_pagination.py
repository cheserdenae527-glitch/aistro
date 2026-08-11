"""作品列表早停与博主资料解析测试。"""
from __future__ import annotations

import sys
from pathlib import Path

from app.services.xhs_user_resolver import parse_profile_from_info

_RUNTIME = (
    Path(__file__).resolve().parents[1]
    / "services" / "crawler" / "xhs" / "scripts" / "runtime" / "spider_xhs_core"
)
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from apis.xhs_pc_apis import XHS_Apis  # noqa: E402


def _page(notes, has_more=True, cursor="c1"):
    return True, "", {"data": {"notes": notes, "has_more": has_more, "cursor": cursor}}


def _fake_apis(page_count: int):
    class _Fake:
        def __init__(self):
            self.calls = 0

        def get_user_note_info(self, user_id, cursor, xsec_token, xsec_source, proxies=None):
            self.calls += 1
            if self.calls >= page_count:
                return _page([{"note_id": f"n{self.calls * 100 + i}"} for i in range(30)], has_more=False, cursor="")
            return _page([{"note_id": f"n{self.calls * 100 + i}"} for i in range(30)])

    return _Fake()


def test_parse_profile_note_count():
    raw = {
        "data": {
            "basic_info": {"nickname": "博主", "note_count": "120"},
            "interactions": [{"type": "fans", "count": 5000}],
        }
    }
    parsed = parse_profile_from_info(raw)
    assert parsed["ok"] is True
    assert parsed["fans"] == 5000
    assert parsed["note_count"] == 120


def test_user_notes_early_stop_truncates():
    fake = _fake_apis(page_count=3)
    success, _msg, notes = XHS_Apis.get_user_all_notes(
        fake,
        "https://www.xiaohongshu.com/user/profile/uid123",
        max_notes=35,
    )
    assert success is True
    assert len(notes) == 35
    assert fake.calls == 2  # 35 篇在第二页就够，不应继续拉第三页


def test_user_notes_no_limit_fetches_all():
    fake = _fake_apis(page_count=3)
    success, _msg, notes = XHS_Apis.get_user_all_notes(
        fake,
        "https://www.xiaohongshu.com/user/profile/uid123",
    )
    assert success is True
    assert len(notes) == 90
    assert fake.calls == 3
