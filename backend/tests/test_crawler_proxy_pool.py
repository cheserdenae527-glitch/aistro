"""多 IP 代理池配置与轮换测试（纯逻辑，不发起真实网络请求）。"""
from __future__ import annotations

import io
import json
import time

import pytest

from crawler import config
from crawler import xhs as xhs_module
from crawler.xhs import XhsCrawler


def test_tunnel_multi_sid_builds_one_proxy_per_channel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("XHS_TUNNEL_BACKUP_HOST", raising=False)
    monkeypatch.delenv("XHS_TUNNEL_BACKUP_HTTP_PORT", raising=False)
    monkeypatch.setenv("XHS_TUNNEL_USERNAME", "user")
    monkeypatch.setenv("XHS_TUNNEL_PASSWORD", "pass")
    monkeypatch.setenv("XHS_TUNNEL_HOST", "a329.zdtps.com")
    monkeypatch.setenv("XHS_TUNNEL_HTTP_PORT", "21166")
    monkeypatch.setenv("XHS_TUNNEL_PERIOD", "60")
    monkeypatch.setenv("XHS_TUNNEL_POOL", "enh")
    monkeypatch.setenv("XHS_TUNNEL_SIDS", "aa0001,ab0002")

    pool = config.get_tunnel_proxies()
    assert len(pool) == 2
    assert "sid-aa0001" in pool[0]["http"]
    assert "sid-ab0002" in pool[1]["http"]
    assert pool[0]["https"] == pool[0]["http"]


def test_tunnel_backup_host_adds_second_entry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XHS_TUNNEL_USERNAME", "user")
    monkeypatch.setenv("XHS_TUNNEL_PASSWORD", "pass")
    monkeypatch.setenv("XHS_TUNNEL_HOST", "a329.zdtps.com")
    monkeypatch.setenv("XHS_TUNNEL_HTTP_PORT", "21166")
    monkeypatch.setenv("XHS_TUNNEL_BACKUP_HOST", "a592.zdtps.com")
    monkeypatch.setenv("XHS_TUNNEL_BACKUP_HTTP_PORT", "21166")

    pool = config.get_tunnel_proxies()
    assert len(pool) == 2
    assert "a329.zdtps.com" in pool[0]["http"]
    assert "a592.zdtps.com" in pool[1]["http"]
    stats = config.proxy_pool_stats()
    assert stats["tunnel_hosts"] == ["a329.zdtps.com:21166", "a592.zdtps.com:21166"]


def test_short_proxy_json_parsed_into_requests_style(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("XHS_SHORT_PROXY_USERNAME", raising=False)
    monkeypatch.delenv("XHS_SHORT_PROXY_PASSWORD", raising=False)
    monkeypatch.setenv("XHS_SHORT_PROXY_API", "http://open.test/ShortProxy/GetIP/")
    monkeypatch.setenv("XHS_SHORT_PROXY_API_ID", "12345")
    monkeypatch.setenv("XHS_SHORT_PROXY_AKEY", "abcdef0123456789")
    monkeypatch.setenv("XHS_SHORT_PROXY_COUNT", "2")
    monkeypatch.setenv("XHS_SHORT_PROXY_TIMESPAN", "3")
    monkeypatch.setattr(config, "_short_proxy_cache", None)

    seen_url = {}

    def fake_urlopen(req, timeout=10):
        seen_url["url"] = req.full_url
        payload = {
            "code": "10001",
            "msg": "获取成功",
            "data": {
                "count": 2,
                "proxy_list": [
                    {"ip": "1.2.3.4", "port": 8080, "timeout": 277},
                    {"ip": "5.6.7.8", "port": 9090, "timeout": 186},
                ],
            },
        }
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(config.urllib.request, "urlopen", fake_urlopen)
    pool = config._fetch_short_proxy_pool()
    assert len(pool) == 2
    assert pool[0]["http"] == "http://1.2.3.4:8080"
    assert pool[1]["https"] == "http://5.6.7.8:9090"
    assert "api=12345" in seen_url["url"]
    assert "count=2" in seen_url["url"]
    assert "timespan=3" in seen_url["url"]


def test_short_proxy_pool_cache_avoids_repeated_getip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XHS_SHORT_PROXY_API", "http://open.test/ShortProxy/GetIP/")
    monkeypatch.setenv("XHS_SHORT_PROXY_API_ID", "12345")
    monkeypatch.setenv("XHS_SHORT_PROXY_AKEY", "abcdef0123456789")
    monkeypatch.setenv("XHS_SHORT_PROXY_REFRESH_SECONDS", "120")
    cached = [{"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"}]
    monkeypatch.setattr(config, "_short_proxy_cache", (time.monotonic(), cached))

    def fake_urlopen(req, timeout=10):
        raise AssertionError("缓存命中时不应再次调用 GetIP")

    monkeypatch.setattr(config.urllib.request, "urlopen", fake_urlopen)
    assert config.get_short_proxy_pool() == cached


def test_proxy_pool_rotates_globally_across_instances(monkeypatch: pytest.MonkeyPatch):
    pool = [
        {"http": "http://proxy-a:1", "https": "http://proxy-a:1"},
        {"http": "http://proxy-b:2", "https": "http://proxy-b:2"},
    ]
    monkeypatch.setattr(xhs_module, "_PROXY_PICK_INDEX", 0)
    assert xhs_module._pick_proxy(pool)["http"] == "http://proxy-a:1"
    assert xhs_module._pick_proxy(pool)["http"] == "http://proxy-b:2"


def test_execute_releases_session_proxy_after_operation(monkeypatch: pytest.MonkeyPatch):
    crawler = XhsCrawler("cookie", proxy_pool=[{"http": "http://proxy-a:1"}])
    crawler._active_proxy = {"http": "http://proxy-a:1"}

    def fake_impl(*args, **kwargs):
        return type("R", (), {"success": True, "data": []})()

    monkeypatch.setattr(crawler, "_execute_impl", fake_impl)
    crawler._execute(lambda: None)
    assert crawler._active_proxy is None
