"""
爬虫配置 — Cookie 与代理池管理。
"""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.request
from urllib.parse import parse_qs, quote, urlencode, urlparse

from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_ENV_PATH)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "crawler_config.json")

logger = logging.getLogger("crawler.config")

_SHORT_PROXY_CACHE_LOCK = threading.Lock()
_short_proxy_cache: tuple[float, list[dict]] | None = None

DEFAULT_CONFIG = {
    "cookies": "",
    "proxies": [],
    "min_delay": 2.0,
    "max_delay": 5.0,
    "max_retries": 3,
    "subscription_refresh_interval_hours": 12,
    "subscription_refresh_batch_size": 20,
    "risk_min_interval": 1.0,
    "risk_failure_threshold": 3,
    "risk_cooldown_seconds": 180,
    "min_follower_count": 0,
    "min_note_count": 10,
    "min_avg_likes": 50,
    "analysis_batch_size": 50,
    "analysis_batch_interval_seconds": 2,
    "analysis_detail_concurrency": 2,
    "analysis_max_notes_per_task": 150,
    "analysis_task_timeout_minutes": 45,
    "subscription_deep_sync_min_interval_hours": 24,
    "subscription_deep_sync_max_per_run": 200,
    "blogger_scoring": {
        "weights": {
            "seeding_depth": 0.30, "verticality": 0.20, "stable_output": 0.20,
            "sustained_operation": 0.15, "growth_trend": 0.15,
        },
        "tiers": {
            "T1": {"min": 1000, "max": 10000, "min_healthy_rate": 1.0, "growth_baseline": 0.06},
            "T2": {"min": 10000, "max": 100000, "min_healthy_rate": 0.6, "growth_baseline": 0.09},
            "T3": {"min": 100000, "max": 1000000, "min_healthy_rate": 0.3, "growth_baseline": 0.08},
            "T4": {"min": 1000000, "max": None, "min_healthy_rate": 0.15, "growth_baseline": 0.07},
        },
        "verticality": {"food_keywords": ["探店", "美食", "好吃", "打卡", "菜单", "套餐", "口味", "推荐", "人气", "排队", "新店", "必吃", "餐厅", "小吃", "甜品", "咖啡", "奶茶", "火锅", "烧烤"]},
        "viral": {"median_multiplier": 3.0, "abs_min": 200},
        "stability": {"gap_days": 14, "cliff_drop": 0.5, "cliff_penalty": 25},
        "comments": {
            "intent_keywords": ["在哪", "多少钱", "好吃吗", "怎么去", "求地址", "人均", "哪里", "电话", "营业", "菜单"],
            "spam_keywords": ["太棒了", "学习了", "支持", "求链接", "已收藏", "点赞"],
            "negative_keywords": ["广告", "取关", "踩雷", "差评", "失望"],
            "note_limit": 8,
            "per_note": 50,
        },
        "gate": {
            "stale_days": 60, "fake_ratio": 0.20, "fake_extra_ratio": 0.005,
            "collect_like_ratio_floor": 0.2, "spam_ratio_threshold": 0.5, "growth_spike": 0.20,
            "growth_interaction_drop": 0.2, "t1_growth_spike": 0.35,
        },
        "stage": {"cold_start_fans": 5000, "mature_fans": 10000, "large_fans": 100000},
    },
}


def load_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # merge defaults
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_cookie() -> str:
    """从 Cookie 池选取一个可用 Cookie；池为空时回退旧配置。"""
    from crawler.cookie_pool import pick_cookie

    entry = pick_cookie()
    if entry and entry.get("cookie"):
        return entry["cookie"]
    cfg = load_config()
    if cfg.get("cookies"):
        return cfg["cookies"]
    # fallback to payload_user.json
    fallback = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "payload_user.json")
    if os.path.exists(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            return json.load(f).get("cookies_str", "")
    return ""


def acquire_cookie() -> tuple[str, str | None, list[dict] | None]:
    """返回 (cookie, cookie_id, sticky_proxy_pool)。

    优先从 Cookie 池取号并绑定粘性代理；池为空时回退旧配置，
    cookie_id 为 None，代理池退回全局代理池。
    """
    from crawler.cookie_pool import pick_cookie_with_proxy

    proxy_pool = get_proxy_pool()
    entry, sticky_pool = pick_cookie_with_proxy(proxy_pool)
    if entry and entry.get("cookie"):
        return entry["cookie"], entry.get("id"), sticky_pool
    return get_cookie(), None, proxy_pool


def _tunnel_sid_list() -> list[str]:
    """返回隧道多通道 sid 列表；未配置多通道时为空列表。"""
    raw = os.getenv("XHS_TUNNEL_SIDS", "").replace("，", ",").strip()
    sids = [sid.strip() for sid in raw.split(",") if sid.strip()]
    legacy = os.getenv("XHS_TUNNEL_SID", "").strip()
    if legacy and legacy not in sids:
        sids.append(legacy)
    return sids


def _tunnel_hosts() -> list[tuple[str, str]]:
    """返回隧道入口 (host, port) 列表：主入口 + 可选备用入口。"""
    primary_host = os.getenv("XHS_TUNNEL_HOST", "").strip()
    primary_port = os.getenv("XHS_TUNNEL_HTTP_PORT", "").strip() or os.getenv("XHS_TUNNEL_PORT", "").strip()
    hosts = []
    if primary_host and primary_port:
        hosts.append((primary_host, primary_port))
    backup_host = os.getenv("XHS_TUNNEL_BACKUP_HOST", "").strip()
    backup_port = os.getenv("XHS_TUNNEL_BACKUP_HTTP_PORT", "").strip() or primary_port
    if backup_host and backup_port:
        hosts.append((backup_host, backup_port))
    return hosts


def _tunnel_proxy(host: str, port: str, sid: str | None) -> dict | None:
    """构造站大爷隧道代理（HTTP 入口），配置齐全时返回 requests 风格 proxies。"""
    username = os.getenv("XHS_TUNNEL_USERNAME", "").strip()
    password = os.getenv("XHS_TUNNEL_PASSWORD", "").strip()
    if not (username and password and host and port):
        return None
    user_part = username
    period = os.getenv("XHS_TUNNEL_PERIOD", "").strip()
    if period:
        user_part += f"-period-{period}"
    pool = os.getenv("XHS_TUNNEL_POOL", "").strip()
    if pool:
        user_part += f"-pool-{pool}"
    region = os.getenv("XHS_TUNNEL_REGION", "").strip().lstrip("-")
    if region:
        user_part += f"-{region}"
    if sid:
        user_part += f"-sid-{sid}"
    url = f"http://{quote(user_part, safe='-')}:{quote(password, safe='')}@{host}:{port}"
    return {"http": url, "https": url, "host": host, "port": port, "sid": sid or ""}


def get_tunnel_proxies() -> list[dict]:
    """返回隧道代理池；主/备入口 × sid 组合成多条通道。"""
    sids = _tunnel_sid_list() or [None]
    proxies = []
    for host, port in _tunnel_hosts():
        for sid in sids:
            proxy = _tunnel_proxy(host, port, sid)
            if proxy:
                proxies.append(proxy)
    return proxies


def get_tunnel_proxy() -> dict | None:
    """兼容旧接口：返回隧道代理池中的第一个代理。"""
    proxies = get_tunnel_proxies()
    return proxies[0] if proxies else None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _short_proxy_request_url() -> str | None:
    """构造短效代理 GetIP 请求；支持直接粘贴控制台生成的完整提取链接。"""
    url = os.getenv("XHS_SHORT_PROXY_API", "").strip()
    if not url:
        return None
    if "api" in parse_qs(urlparse(url).query):
        return url
    api_id = os.getenv("XHS_SHORT_PROXY_API_ID", "").strip()
    akey = os.getenv("XHS_SHORT_PROXY_AKEY", "").strip()
    password = os.getenv("XHS_SHORT_PROXY_PASSWORD", "").strip()
    if not akey and password:
        akey = hashlib.md5(password.encode("utf-8")).hexdigest()
    if not (api_id and akey):
        return None
    params = {
        "api": api_id,
        "akey": akey,
        "count": str(_env_int("XHS_SHORT_PROXY_COUNT", 5)),
        "timespan": str(_env_int("XHS_SHORT_PROXY_TIMESPAN", 3)),
        "type": "3",
    }
    sep = "&" if urlparse(url).query else "?"
    return url + sep + urlencode(params)


def _fetch_short_proxy_pool() -> list[dict]:
    """调用站大爷短效代理 GetIP，返回 requests 风格 proxies 列表。"""
    request_url = _short_proxy_request_url()
    if not request_url:
        return []
    req = urllib.request.Request(request_url, headers={"User-Agent": "AiRestro/0.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    code = str(payload.get("code", ""))
    if code != "10001":
        raise RuntimeError(f"短效代理获取失败: {payload.get('msg') or code}")
    raw_list = ((payload.get("data") or {}).get("proxy_list")) or []
    proxies = []
    for item in raw_list:
        ip = str(item.get("ip", "")).strip()
        port = str(item.get("port", "")).strip()
        if not ip or not port:
            continue
        url = f"http://{ip}:{port}"
        proxies.append({
            "http": url,
            "https": url,
            "source": "short_proxy",
            "timeout": item.get("timeout"),
        })
    return proxies


def get_short_proxy_pool() -> list[dict]:
    """短效代理池：进程内缓存，避免高频调用 GetIP；失败时回退旧池。"""
    global _short_proxy_cache
    now = time.monotonic()
    ttl = _env_int("XHS_SHORT_PROXY_REFRESH_SECONDS", 90)
    with _SHORT_PROXY_CACHE_LOCK:
        if _short_proxy_cache and now - _short_proxy_cache[0] < ttl:
            return list(_short_proxy_cache[1])
    try:
        proxies = _fetch_short_proxy_pool()
    except Exception as exc:
        logger.warning("短效代理池刷新失败: %s", exc)
        with _SHORT_PROXY_CACHE_LOCK:
            if _short_proxy_cache:
                return list(_short_proxy_cache[1])
            # 失败也短暂缓存空池，避免每个请求都重复打 GetIP
            _short_proxy_cache = (now, [])
        return []
    with _SHORT_PROXY_CACHE_LOCK:
        _short_proxy_cache = (now, proxies)
    return list(proxies)


def get_proxy_pool() -> list[dict]:
    tunnels = get_tunnel_proxies()
    if tunnels:
        return tunnels
    short_proxies = get_short_proxy_pool()
    if short_proxies:
        return short_proxies
    cfg = load_config()
    return cfg.get("proxies", [])


def _proxy_label(proxy: dict) -> str:
    url = str((proxy or {}).get("http") or (proxy or {}).get("https") or "")
    if "@" in url:
        return url.rsplit("@", 1)[-1]
    return url


def proxy_pool_stats() -> dict:
    """返回代理池概览，供管理界面展示（不含凭据明文）。"""
    tunnels = get_tunnel_proxies()
    short = get_short_proxy_pool()
    cfg = load_config()
    static = cfg.get("proxies", []) or []
    if tunnels:
        source = "tunnel"
        entries = [{"label": _proxy_label(p), "source": "tunnel"} for p in tunnels]
    elif short:
        source = "short_proxy"
        entries = [{"label": _proxy_label(p), "source": "short_proxy"} for p in short]
    elif static:
        source = "static"
        entries = [{"label": _proxy_label(p), "source": "static"} for p in static]
    else:
        source = "none"
        entries = []
    return {
        "source": source,
        "count": len(entries),
        "entries": entries,
        "tunnel_hosts": [f"{h}:{p}" for h, p in _tunnel_hosts()],
        "tunnel_sids": _tunnel_sid_list(),
        "tunnel_period_seconds": os.getenv("XHS_TUNNEL_PERIOD", "").strip(),
        "tunnel_pool": os.getenv("XHS_TUNNEL_POOL", "").strip(),
        "short_proxy_refresh_seconds": _env_int("XHS_SHORT_PROXY_REFRESH_SECONDS", 90),
        "static_count": len(static),
    }


def refresh_short_proxies() -> list[dict]:
    """强制刷新短效代理池（清缓存后重新 GetIP）。"""
    global _short_proxy_cache
    with _SHORT_PROXY_CACHE_LOCK:
        _short_proxy_cache = None
    return get_short_proxy_pool()


def recent_request_logs(limit: int = 50) -> list[dict]:
    """返回最近的爬虫请求调用记录，并补上对应的 Cookie 名称。"""
    from crawler.cookie_pool import list_cookies

    log_path = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "crawl_request_log.jsonl")
    labels = {c["id"]: c["label"] for c in list_cookies()}
    items: list[dict] = []
    if not os.path.exists(log_path):
        return items
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            cookie_id = rec.get("cookie_id") or ""
            rec["cookie_label"] = labels.get(cookie_id, "") if cookie_id else ""
            items.append(rec)
    except Exception:
        pass
    return items


def get_delay_settings() -> tuple[float, float, int]:
    cfg = load_config()
    return cfg.get("min_delay", 2.0), cfg.get("max_delay", 5.0), cfg.get("max_retries", 3)




