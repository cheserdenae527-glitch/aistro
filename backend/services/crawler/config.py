"""
爬虫配置 — Cookie 与代理池管理。
"""

import json
import os

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


def get_proxy_pool() -> list[dict]:
    cfg = load_config()
    return cfg.get("proxies", [])


def get_delay_settings() -> tuple[float, float, int]:
    cfg = load_config()
    return cfg.get("min_delay", 2.0), cfg.get("max_delay", 5.0), cfg.get("max_retries", 3)




