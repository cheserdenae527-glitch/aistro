"""
爬虫配置 — Cookie 与代理池管理。
"""

import json
import os
from urllib.parse import quote

from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_ENV_PATH)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "crawler_config.json")

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
    "analysis_batch_interval_seconds": 5,
    "analysis_max_notes_per_task": 150,
    "analysis_task_timeout_minutes": 45,
    "subscription_deep_sync_min_interval_hours": 24,
    "subscription_deep_sync_max_per_run": 200,
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
    cfg = load_config()
    if cfg.get("cookies"):
        return cfg["cookies"]
    # fallback to payload_user.json
    fallback = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "payload_user.json")
    if os.path.exists(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            return json.load(f).get("cookies_str", "")
    return ""


def get_tunnel_proxy() -> dict | None:
    """构造站大爷隧道代理（HTTP 入口），配置齐全时返回 requests 风格 proxies。"""
    username = os.getenv("XHS_TUNNEL_USERNAME", "").strip()
    password = os.getenv("XHS_TUNNEL_PASSWORD", "").strip()
    host = os.getenv("XHS_TUNNEL_HOST", "").strip()
    port = os.getenv("XHS_TUNNEL_HTTP_PORT", "").strip() or os.getenv("XHS_TUNNEL_PORT", "").strip()
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
    sid = os.getenv("XHS_TUNNEL_SID", "").strip()
    if sid:
        user_part += f"-sid-{sid}"
    url = f"http://{quote(user_part, safe='-')}:{quote(password, safe='')}@{host}:{port}"
    return {"http": url, "https": url}


def get_proxy_pool() -> list[dict]:
    tunnel = get_tunnel_proxy()
    if tunnel:
        return [tunnel]
    cfg = load_config()
    return cfg.get("proxies", [])


def get_delay_settings() -> tuple[float, float, int]:
    cfg = load_config()
    return cfg.get("min_delay", 2.0), cfg.get("max_delay", 5.0), cfg.get("max_retries", 3)




