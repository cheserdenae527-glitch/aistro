"""JustOneAPI 客户端解析与合并测试。"""
from __future__ import annotations

import httpx

from app.services import justoneapi_client


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_fetch_parses_platform_history(monkeypatch):
    monkeypatch.setattr(justoneapi_client, "_cache_read", lambda uid: None)
    monkeypatch.setattr(justoneapi_client, "_cache_write", lambda uid, data: None)

    payload = {
        "code": 0,
        "data": {
            "fansNumInc": 500,
            "fansNumIncRate": 0.05,
            "list": [
                {"num": 10000, "dateKey": "2026-06-01"},
                {"num": 10300, "dateKey": "2026-07-01"},
                {"num": 10500, "dateKey": "2026-08-10"},
            ],
        },
        "message": None,
    }

    def fake_get(url: str, **kwargs):
        assert "fans_overall_new_history" in url
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    out = justoneapi_client.fetch_follower_history("uid-123")
    assert out["ok"] is True
    assert out["error"] == ""
    assert len(out["history"]) == 3
    assert out["history"][0] == {
        "fans": 10000,
        "snapshot_at": "2026-06-01T00:00:00+08:00",
        "source": "justoneapi",
    }
    assert out["summary"]["growth_rate"] == 0.05
    assert out["summary"]["points"] == 3


def test_fetch_handles_business_error(monkeypatch):
    monkeypatch.setattr(justoneapi_client, "_cache_read", lambda uid: None)
    monkeypatch.setattr(justoneapi_client, "_cache_write", lambda uid, data: None)

    payload = {"code": 601, "data": None, "message": "balance insufficient"}

    def fake_get(url: str, **kwargs):
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    out = justoneapi_client.fetch_follower_history("uid-123")
    assert out["ok"] is False
    assert out["history"] == []
    assert "601" in out["error"]


def test_merge_prefers_platform_and_keeps_local_gap():
    local = [
        {"fans": 9900, "snapshot_at": "2026-05-01T00:00:00+08:00"},
        # UTC 快照对应北京时间 6 月 1 日，应被平台同日数据覆盖
        {"fans": 10100, "snapshot_at": "2026-05-31T16:00:00+00:00"},
    ]
    platform = {
        "ok": True,
        "history": [
            {"fans": 10000, "snapshot_at": "2026-06-01T00:00:00+08:00", "source": "justoneapi"},
            {"fans": 10500, "snapshot_at": "2026-08-10T00:00:00+08:00", "source": "justoneapi"},
        ],
    }
    merged = justoneapi_client.merge_follower_history(local, platform)
    assert [h["snapshot_at"][:10] for h in merged] == ["2026-05-01", "2026-06-01", "2026-08-10"]
    assert merged[0]["source"] == "local"
    assert merged[1]["source"] == "justoneapi"
    assert merged[2]["fans"] == 10500


def test_merge_timezone_alignment():
    local = [{"fans": 9900, "snapshot_at": "2026-06-01T02:00:00+00:00"}]
    platform = {
        "ok": True,
        "history": [{"fans": 10000, "snapshot_at": "2026-06-01T00:00:00+08:00", "source": "justoneapi"}],
    }
    merged = justoneapi_client.merge_follower_history(local, platform)
    assert len(merged) == 1
    assert merged[0]["source"] == "justoneapi"
