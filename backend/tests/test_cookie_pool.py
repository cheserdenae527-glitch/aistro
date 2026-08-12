"""Cookie 池与代理池状态测试（纯逻辑，不发起真实网络请求）。"""
from __future__ import annotations

import pytest

from crawler import config as crawler_config
from crawler import cookie_pool


COOKIE_A = "a1=aaa;web_session=aaa"
COOKIE_B = "a1=bbb;web_session=bbb"


@pytest.fixture(autouse=True)
def isolated_pool(tmp_path, monkeypatch: pytest.MonkeyPatch):
    pool_file = tmp_path / "cookie_pool.json"
    monkeypatch.setattr(cookie_pool, "_POOL_PATH", str(pool_file))
    monkeypatch.setenv("XHS_COOKIE_MAX_CONTINUOUS_FAIL", "2")
    monkeypatch.setenv("XHS_COOKIE_COOLING_SECONDS", "1800")
    monkeypatch.setenv("XHS_COOKIE_MAX_TOTAL_FAIL", "3")
    monkeypatch.setenv("XHS_COOKIE_MAX_USE_PER_HOUR", "2")
    monkeypatch.setenv("XHS_COOKIE_MAX_PROXY_FAILURES", "2")
    monkeypatch.setenv("XHS_COOKIE_PROXY_SESSION_SECONDS", "300")
    yield


def test_validate_requires_a1_and_web_session():
    assert cookie_pool.validate_cookie("a1=1;web_session=2") is None
    assert cookie_pool.validate_cookie("a1=1") is not None
    assert cookie_pool.validate_cookie("") is not None


def test_add_list_update_delete():
    entry = cookie_pool.add_cookie(COOKIE_A, label="账号A")
    assert entry["status"] == "available"
    assert entry["use_count"] == 0
    assert cookie_pool.list_cookies()[0]["id"] == entry["id"]

    updated = cookie_pool.update_cookie(entry["id"], label="新名字", status="paused")
    assert updated["label"] == "新名字"
    assert updated["status"] == "paused"

    assert cookie_pool.delete_cookie(entry["id"]) is True
    assert cookie_pool.list_cookies() == []
    assert cookie_pool.delete_cookie(entry["id"]) is False


def test_add_rejects_invalid_cookie():
    with pytest.raises(ValueError):
        cookie_pool.add_cookie("a1=1")


def test_pick_uses_least_used_and_rotates():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    b = cookie_pool.add_cookie(COOKIE_B, label="B")

    first = cookie_pool.pick_cookie()
    assert first["id"] in (a["id"], b["id"])
    assert first["use_count"] == 1
    assert first["last_used"] is not None

    second = cookie_pool.pick_cookie()
    assert second["id"] != first["id"]
    assert second["use_count"] == 1

    third = cookie_pool.pick_cookie()
    assert third["use_count"] == 2


def test_pick_cookie_with_proxy_binds_and_reuses():
    pool = [
        {"http": "http://proxy-a:1", "https": "http://proxy-a:1"},
        {"http": "http://proxy-b:2", "https": "http://proxy-b:2"},
    ]
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    entry, sticky = cookie_pool.pick_cookie_with_proxy(pool)
    assert entry["id"] == a["id"]
    assert entry["proxy_session_id"] is not None
    assert entry["proxy_expires_at"] is not None
    assert sticky == [entry["proxy"]]

    entry2, sticky2 = cookie_pool.pick_cookie_with_proxy(pool)
    assert entry2["proxy_session_id"] == entry["proxy_session_id"]
    assert sticky2 == sticky


def test_pick_cookie_with_proxy_rebinds_after_expiry():
    pool = [
        {"http": "http://proxy-a:1", "https": "http://proxy-a:1"},
        {"http": "http://proxy-b:2", "https": "http://proxy-b:2"},
    ]
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    entry, _ = cookie_pool.pick_cookie_with_proxy(pool)
    old_session = entry["proxy_session_id"]

    with cookie_pool._LOCK:
        data = cookie_pool._load()
        for c in data["cookies"]:
            if c["id"] == a["id"]:
                c["proxy_expires_at"] = 1
        cookie_pool._save(data)

    entry2, _ = cookie_pool.pick_cookie_with_proxy(pool)
    assert entry2["proxy_session_id"] != old_session
    assert entry2["proxy_session_id"] is not None


def test_proxy_failures_unbind_after_threshold():
    pool = [{"http": "http://proxy-a:1", "https": "http://proxy-a:1"}]
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.pick_cookie_with_proxy(pool)
    cookie_pool.report_result(a["id"], False, "网络错误")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["proxy_session_id"] is not None

    cookie_pool.report_result(a["id"], False, "网络错误")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["proxy_session_id"] is None
    assert entry["proxy"] is None


def test_report_proxy_result_unbinds_without_harming_cookie():
    pool = [{"http": "http://proxy-a:1", "https": "http://proxy-a:1"}]
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.pick_cookie_with_proxy(pool)
    cookie_pool.report_proxy_result(a["id"], False)
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["proxy_session_id"] is not None

    cookie_pool.report_proxy_result(a["id"], False)
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["proxy_session_id"] is None
    assert entry["fail_count"] == 0
    assert entry["continuous_fail"] == 0


def test_unbind_and_rebind_cookie():
    pool = [
        {"http": "http://proxy-a:1", "https": "http://proxy-a:1"},
        {"http": "http://proxy-b:2", "https": "http://proxy-b:2"},
    ]
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    entry, _ = cookie_pool.pick_cookie_with_proxy(pool)
    assert entry["proxy_session_id"] is not None

    unbound = cookie_pool.unbind_cookie(a["id"])
    assert unbound["proxy_session_id"] is None

    rebound = cookie_pool.rebind_cookie(a["id"], pool)
    assert rebound["proxy_session_id"] is not None
    assert rebound["proxy_expires_at"] is not None


def test_hourly_use_limit_blocks_cookie():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.pick_cookie()
    cookie_pool.pick_cookie()
    # max_use_per_hour=2，第三个应该拿不到
    assert cookie_pool.pick_cookie() is None
    # 另一 Cookie 不受影响
    cookie_pool.add_cookie(COOKIE_B, label="B")
    assert cookie_pool.pick_cookie()["id"] != a["id"]


def test_continuous_fail_enters_cooling():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.report_result(a["id"], False, "登录已过期")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "available"  # 1 次失败未到阈值

    cookie_pool.report_result(a["id"], False, "登录已过期")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "cooling"
    assert entry["cooling_until"] is not None
    assert entry["continuous_fail"] == 0
    assert entry["last_error"] == "登录已过期"
    assert cookie_pool.pick_cookie() is None


def test_total_fail_marks_invalid():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    for _ in range(cookie_pool._config()["max_total_fail"]):
        cookie_pool.report_result(a["id"], False, "失败")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "invalid"
    assert entry["fail_count"] == cookie_pool._config()["max_total_fail"]


def test_success_resets_health():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.report_result(a["id"], False, "风险")
    cookie_pool.report_result(a["id"], True)
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "available"
    assert entry["continuous_fail"] == 0
    assert entry["success_count"] == 1
    assert entry["last_error"] == ""


def test_check_and_recover_restores_cooling():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.report_result(a["id"], False, "风险")
    cookie_pool.report_result(a["id"], False, "风险")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "cooling"

    # 把冷却时间拨到过去
    cookie_pool.update_cookie(a["id"], status="cooling")
    with cookie_pool._LOCK:
        pool = cookie_pool._load()
        for c in pool["cookies"]:
            if c["id"] == a["id"]:
                c["cooling_until"] = 1
        cookie_pool._save(pool)

    recovered = cookie_pool.check_and_recover()
    assert a["id"] in recovered
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["status"] == "available"


def test_remove_invalid():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    for _ in range(cookie_pool._config()["max_total_fail"]):
        cookie_pool.report_result(a["id"], False, "失败")
    assert cookie_pool.remove_invalid() == 1
    assert cookie_pool.list_cookies() == []


def test_reactivate_resets_failure_count():
    a = cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie_pool.report_result(a["id"], False, "风险")
    cookie_pool.update_cookie(a["id"], status="available")
    entry = next(c for c in cookie_pool.list_cookies() if c["id"] == a["id"])
    assert entry["continuous_fail"] == 0
    assert entry["cooling_until"] is None


def test_acquire_cookie_uses_pool_first(monkeypatch: pytest.MonkeyPatch):
    cookie_pool.add_cookie(COOKIE_A, label="A")
    cookie, cookie_id, sticky_pool = crawler_config.acquire_cookie()
    assert cookie == COOKIE_A
    assert cookie_id is not None
    assert sticky_pool is not None


def test_acquire_cookie_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        crawler_config,
        "load_config",
        lambda: {"cookies": "legacy-cookie", "proxies": []},
    )
    monkeypatch.setattr(crawler_config, "get_proxy_pool", lambda: [])
    cookie, cookie_id, sticky_pool = crawler_config.acquire_cookie()
    assert cookie == "legacy-cookie"
    assert cookie_id is None
    assert sticky_pool == []


def test_proxy_pool_stats_with_tunnel(monkeypatch: pytest.MonkeyPatch):
    # 默认代理源（不显式指定 XHS_PROXY_SOURCE 时走 tunnel→short→static 顺序）
    monkeypatch.delenv("XHS_PROXY_SOURCE", raising=False)
    monkeypatch.delenv("XHS_TUNNEL_BACKUP_HOST", raising=False)
    monkeypatch.delenv("XHS_TUNNEL_BACKUP_HTTP_PORT", raising=False)
    monkeypatch.setenv("XHS_TUNNEL_USERNAME", "user")
    monkeypatch.setenv("XHS_TUNNEL_PASSWORD", "pass")
    monkeypatch.setenv("XHS_TUNNEL_HOST", "a329.zdtps.com")
    monkeypatch.setenv("XHS_TUNNEL_HTTP_PORT", "21166")
    monkeypatch.setenv("XHS_TUNNEL_SIDS", "aa0001,ab0002")
    stats = crawler_config.proxy_pool_stats()
    assert stats["source"] == "tunnel"
    assert stats["count"] == 2
    assert all("zdtps.com" in e["label"] for e in stats["entries"])
    assert "aa0001" in stats["tunnel_sids"]
