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
