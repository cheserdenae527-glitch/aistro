"""Cookie 池管理 — 多账号 Cookie 的增删改、健康度与轮换。

策略（小规模自用版）：
- 随机 + 最少使用优先：优先选总使用次数最少的 Cookie，同次数时随机
- 每小时用量限制：单个 Cookie 1 小时内最多使用 max_use_per_hour 次
- 连续失败冷却：连续失败达到 max_continuous_fail 次进入冷却，冷却结束后恢复可用
- 总失败淘汰：总失败次数达到 max_total_fail 次直接标记 invalid
- 文件落盘在 crawler/xhs/scripts/cookie_pool.json，进程内带锁访问

状态机：available ->（失败）-> cooling ->（冷却结束）-> available
                    ->（总失败过多）-> invalid
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("crawler.cookie_pool")

_POOL_PATH = os.path.join(os.path.dirname(__file__), "xhs", "scripts", "cookie_pool.json")
_LOCK = threading.RLock()

REQUIRED_COOKIE_KEYS = ("a1", "web_session")
VALID_STATUSES = ("available", "cooling", "invalid", "paused")
USAGE_WINDOW_SECONDS = 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _config() -> dict:
    """小规模推荐配置，可用环境变量覆盖。"""
    return {
        "max_use_per_hour": _env_int("XHS_COOKIE_MAX_USE_PER_HOUR", 25),
        "max_continuous_fail": _env_int("XHS_COOKIE_MAX_CONTINUOUS_FAIL", 2),
        "cooling_seconds": _env_int("XHS_COOKIE_COOLING_SECONDS", 1800),
        "max_total_fail": _env_int("XHS_COOKIE_MAX_TOTAL_FAIL", 8),
        "proxy_session_seconds": _env_int("XHS_COOKIE_PROXY_SESSION_SECONDS", 300),
        "max_proxy_failures": _env_int("XHS_COOKIE_MAX_PROXY_FAILURES", 2),
    }


def _normalize_entry(entry: dict) -> dict:
    """把旧版字段迁移/补齐成新版结构。"""
    entry.setdefault("label", "")
    entry.setdefault("cookie", "")
    status = str(entry.get("status", "available"))
    if status == "active":
        status = "available"
    elif status == "disabled":
        status = "invalid"
    elif status not in VALID_STATUSES:
        status = "available"
    entry["status"] = status
    entry.setdefault("use_count", 0)
    entry.setdefault("success_count", 0)
    entry.setdefault("fail_count", int(entry.get("failure_count", 0)))
    entry.setdefault("continuous_fail", int(entry.get("failure_count", 0)))
    entry.setdefault("last_used", None)
    entry.setdefault("last_success", None)
    entry.setdefault("cooling_until", None)
    entry.setdefault("usage_history", [])
    entry.setdefault("last_error", "")
    entry.setdefault("proxy_session_id", None)
    entry.setdefault("proxy", None)
    entry.setdefault("proxy_bound_at", None)
    entry.setdefault("proxy_expires_at", None)
    entry.setdefault("proxy_failures", 0)
    entry.setdefault("created_at", _now_iso())
    entry.setdefault("updated_at", _now_iso())
    entry.pop("failure_count", None)
    entry.pop("last_used_at", None)
    return entry


def _load() -> dict:
    if not os.path.exists(_POOL_PATH):
        return {"cookies": [], "updated_at": _now_iso()}
    try:
        with open(_POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("cookies"), list):
            raise ValueError("bad pool shape")
        data["cookies"] = [_normalize_entry(c) for c in data["cookies"]]
        return data
    except Exception:
        logger.warning("Cookie 池文件损坏，已重置为空池: %s", _POOL_PATH)
        return {"cookies": [], "updated_at": _now_iso()}


def _save(pool: dict) -> None:
    pool["updated_at"] = _now_iso()
    tmp = _POOL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _POOL_PATH)


def validate_cookie(cookie: str) -> str | None:
    """基础校验：必须包含签名与登录态必需的字段，返回错误信息或 None。"""
    if not cookie or not cookie.strip():
        return "Cookie 不能为空"
    keys = {part.split("=", 1)[0].strip() for part in cookie.split(";") if "=" in part}
    missing = [k for k in REQUIRED_COOKIE_KEYS if k not in keys]
    if missing:
        return "Cookie 缺少关键字段: " + ", ".join(missing)
    return None


def list_cookies() -> list[dict]:
    with _LOCK:
        return [dict(c) for c in _load().get("cookies", [])]


def pool_stats() -> dict:
    """返回池状态概览，供管理界面展示。"""
    with _LOCK:
        cookies = _load().get("cookies", [])
    counts = {"available": 0, "cooling": 0, "invalid": 0, "paused": 0}
    total_use = 0
    total_success = 0
    total_fail = 0
    for c in cookies:
        counts[c.get("status", "available")] = counts.get(c.get("status", "available"), 0) + 1
        total_use += int(c.get("use_count", 0))
        total_success += int(c.get("success_count", 0))
        total_fail += int(c.get("fail_count", 0))
    cfg = _config()
    return {
        "total": len(cookies),
        "counts": counts,
        "total_use": total_use,
        "total_success": total_success,
        "total_fail": total_fail,
        "config": cfg,
        "usage_window_seconds": USAGE_WINDOW_SECONDS,
        "updated_at": _load().get("updated_at", ""),
    }


def add_cookie(cookie: str, label: str = "") -> dict:
    """添加一个 Cookie 到池中；自动生成唯一 id 并置为 available。"""
    error = validate_cookie(cookie)
    if error:
        raise ValueError(error)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "label": label.strip() or f"账号 {len(list_cookies()) + 1}",
        "cookie": cookie.strip(),
        "status": "available",
        "use_count": 0,
        "success_count": 0,
        "fail_count": 0,
        "continuous_fail": 0,
        "last_used": None,
        "last_success": None,
        "cooling_until": None,
        "usage_history": [],
        "last_error": "",
        "proxy_session_id": None,
        "proxy": None,
        "proxy_bound_at": None,
        "proxy_expires_at": None,
        "proxy_failures": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    with _LOCK:
        pool = _load()
        pool.setdefault("cookies", []).append(entry)
        _save(pool)
    return dict(entry)


def update_cookie(
    cookie_id: str,
    *,
    label: str | None = None,
    cookie: str | None = None,
    status: str | None = None,
) -> dict | None:
    """按 id 更新 Cookie 的 label/cookie/status；返回更新后的条目或 None。"""
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("status 必须是 available/cooling/invalid/paused")
    if cookie is not None:
        error = validate_cookie(cookie)
        if error:
            raise ValueError(error)
    with _LOCK:
        pool = _load()
        for entry in pool.get("cookies", []):
            if entry.get("id") != cookie_id:
                continue
            if label is not None:
                entry["label"] = label.strip() or entry.get("label", "")
            if cookie is not None:
                entry["cookie"] = cookie.strip()
            if status is not None:
                entry["status"] = status
                if status == "available":
                    entry["continuous_fail"] = 0
                    entry["cooling_until"] = None
                    entry["last_error"] = ""
                    _clear_proxy_binding(entry)
                elif status == "cooling":
                    entry["cooling_until"] = int(time.time()) + _config()["cooling_seconds"]
                elif status == "invalid":
                    entry["cooling_until"] = None
                    _clear_proxy_binding(entry)
            entry["updated_at"] = _now_iso()
            _save(pool)
            return dict(entry)
    return None


def delete_cookie(cookie_id: str) -> bool:
    with _LOCK:
        pool = _load()
        before = len(pool.get("cookies", []))
        pool["cookies"] = [c for c in pool.get("cookies", []) if c.get("id") != cookie_id]
        if len(pool["cookies"]) == before:
            return False
        _save(pool)
        return True


def _prune_usage(entry: dict, now: int) -> list[int]:
    raw = entry.get("usage_history") or []
    return [int(t) for t in raw if now - int(t) < USAGE_WINDOW_SECONDS]


def _proxy_key(proxy: dict | None) -> str:
    return str((proxy or {}).get("http") or (proxy or {}).get("https") or "")


def _clear_proxy_binding(entry: dict) -> None:
    entry["proxy_session_id"] = None
    entry["proxy"] = None
    entry["proxy_bound_at"] = None
    entry["proxy_expires_at"] = None
    entry["proxy_failures"] = 0


def _pick_new_proxy(pool: list[dict], taken_urls: set[str]) -> dict | None:
    """从代理池挑选一个未被其他可用 Cookie 占用的代理。"""
    usable = [
        p for p in (pool or [])
        if _proxy_key(p) and _proxy_key(p) not in taken_urls
    ]
    if not usable:
        usable = [p for p in (pool or []) if _proxy_key(p)]
    if not usable:
        return None
    return random.choice(usable)


def pick_cookie() -> dict | None:
    """随机 + 最少使用优先：优先选总使用次数最少的可用 Cookie。"""
    check_and_recover()
    now = int(time.time())
    cfg = _config()
    with _LOCK:
        pool = _load()
        candidates = []
        for entry in pool.get("cookies", []):
            if entry.get("status") != "available" or not entry.get("cookie"):
                continue
            if entry.get("cooling_until") and int(entry.get("cooling_until") or 0) > now:
                continue
            history = _prune_usage(entry, now)
            if len(history) >= int(cfg["max_use_per_hour"]):
                continue
            entry["usage_history"] = history
            candidates.append(entry)
        if not candidates:
            return None
        candidates.sort(key=lambda c: (int(c.get("use_count", 0)), random.random()))
        chosen = candidates[0]
        chosen["use_count"] = int(chosen.get("use_count", 0)) + 1
        chosen["last_used"] = now
        chosen["usage_history"] = chosen.get("usage_history", []) + [now]
        chosen["updated_at"] = _now_iso()
        _save(pool)
        return dict(chosen)


def pick_cookie_with_proxy(pool: list[dict]) -> tuple[dict | None, list[dict] | None]:
    """选取 Cookie 并返回粘性代理池（单元素列表）。

    若 Cookie 已有未过期的代理 session 则继续沿用；否则分配新 session 并记录绑定。
    """
    check_and_recover()
    now = int(time.time())
    cfg = _config()
    with _LOCK:
        pool_data = _load()
        candidates = []
        for entry in pool_data.get("cookies", []):
            if entry.get("status") != "available" or not entry.get("cookie"):
                continue
            if entry.get("cooling_until") and int(entry.get("cooling_until") or 0) > now:
                continue
            history = _prune_usage(entry, now)
            if len(history) >= int(cfg["max_use_per_hour"]):
                continue
            entry["usage_history"] = history
            candidates.append(entry)
        if not candidates:
            return None, None
        candidates.sort(key=lambda c: (int(c.get("use_count", 0)), random.random()))
        chosen = candidates[0]
        chosen["use_count"] = int(chosen.get("use_count", 0)) + 1
        chosen["last_used"] = now
        chosen["usage_history"] = chosen.get("usage_history", []) + [now]
        chosen["updated_at"] = _now_iso()

        bound = chosen.get("proxy") or {}
        session_valid = (
            chosen.get("proxy_session_id")
            and chosen.get("proxy_expires_at")
            and int(chosen["proxy_expires_at"]) > now
            and _proxy_key(bound)
        )
        if session_valid:
            proxy = bound
        else:
            taken = {
                _proxy_key(c.get("proxy") or {})
                for c in pool_data.get("cookies", [])
                if c.get("id") != chosen.get("id") and c.get("status") == "available"
            }
            proxy = _pick_new_proxy(pool, taken)
            if proxy:
                chosen["proxy_session_id"] = uuid.uuid4().hex[:12]
                chosen["proxy"] = proxy
                chosen["proxy_bound_at"] = now
                chosen["proxy_expires_at"] = now + int(cfg["proxy_session_seconds"])
                chosen["proxy_failures"] = 0
            else:
                _clear_proxy_binding(chosen)
        _save(pool_data)
        return dict(chosen), [proxy] if proxy else None


def report_result(cookie_id: str, success: bool, error: str = "") -> dict | None:
    """回写 Cookie 采集结果：连续失败冷却、总失败淘汰、成功恢复。"""
    if not cookie_id:
        return None
    now = int(time.time())
    cfg = _config()
    with _LOCK:
        pool = _load()
        for entry in pool.get("cookies", []):
            if entry.get("id") != cookie_id:
                continue
            entry["updated_at"] = _now_iso()
            if success:
                entry["success_count"] = int(entry.get("success_count", 0)) + 1
                entry["continuous_fail"] = 0
                entry["last_success"] = now
                entry["last_error"] = ""
                entry["status"] = "available"
                entry["cooling_until"] = None
                entry["proxy_failures"] = 0
            else:
                entry["fail_count"] = int(entry.get("fail_count", 0)) + 1
                entry["continuous_fail"] = int(entry.get("continuous_fail", 0)) + 1
                entry["proxy_failures"] = int(entry.get("proxy_failures", 0)) + 1
                entry["last_error"] = str(error)[:300]
                if entry["continuous_fail"] >= int(cfg["max_continuous_fail"]):
                    entry["status"] = "cooling"
                    entry["cooling_until"] = now + int(cfg["cooling_seconds"])
                    entry["continuous_fail"] = 0
                if entry["fail_count"] >= int(cfg["max_total_fail"]):
                    entry["status"] = "invalid"
                    entry["cooling_until"] = None
                    _clear_proxy_binding(entry)
                elif entry["proxy_failures"] >= int(cfg["max_proxy_failures"]):
                    _clear_proxy_binding(entry)
            _save(pool)
            return dict(entry)
    return None


def report_proxy_result(cookie_id: str, success: bool) -> dict | None:
    """单独回写代理健康度：失败计数达到阈值就解绑，不影响 Cookie 本身健康度。"""
    if not cookie_id:
        return None
    cfg = _config()
    with _LOCK:
        pool = _load()
        for entry in pool.get("cookies", []):
            if entry.get("id") != cookie_id:
                continue
            entry["updated_at"] = _now_iso()
            if success:
                entry["proxy_failures"] = 0
            else:
                entry["proxy_failures"] = int(entry.get("proxy_failures", 0)) + 1
                if entry["proxy_failures"] >= int(cfg["max_proxy_failures"]):
                    _clear_proxy_binding(entry)
            _save(pool)
            return dict(entry)
    return None


def unbind_cookie(cookie_id: str) -> dict | None:
    """手动解除当前 Cookie 的代理绑定；返回更新后的条目或 None。"""
    with _LOCK:
        pool = _load()
        for entry in pool.get("cookies", []):
            if entry.get("id") != cookie_id:
                continue
            _clear_proxy_binding(entry)
            entry["updated_at"] = _now_iso()
            _save(pool)
            return dict(entry)
    return None


def rebind_cookie(cookie_id: str, proxy_pool: list[dict]) -> dict | None:
    """立即为 Cookie 重新分配一个粘性代理；无可用代理时保持原状。"""
    with _LOCK:
        pool = _load()
        for entry in pool.get("cookies", []):
            if entry.get("id") != cookie_id:
                continue
            taken = {
                _proxy_key(c.get("proxy") or {})
                for c in pool.get("cookies", [])
                if c.get("id") != cookie_id and c.get("status") == "available"
            }
            proxy = _pick_new_proxy(proxy_pool, taken)
            if not proxy:
                return dict(entry)
            now = int(time.time())
            entry["proxy_session_id"] = uuid.uuid4().hex[:12]
            entry["proxy"] = proxy
            entry["proxy_bound_at"] = now
            entry["proxy_expires_at"] = now + int(_config()["proxy_session_seconds"])
            entry["proxy_failures"] = 0
            entry["updated_at"] = _now_iso()
            _save(pool)
            return dict(entry)
    return None


def check_and_recover() -> list[str]:
    """冷却到期后恢复为可用；返回本次恢复的 Cookie id。"""
    now = int(time.time())
    recovered: list[str] = []
    with _LOCK:
        pool = _load()
        changed = False
        for entry in pool.get("cookies", []):
            if (
                entry.get("status") == "cooling"
                and int(entry.get("cooling_until") or 0) <= now
            ):
                entry["status"] = "available"
                entry["cooling_until"] = None
                entry["continuous_fail"] = 0
                entry["updated_at"] = _now_iso()
                recovered.append(entry.get("id", ""))
                changed = True
        if changed:
            _save(pool)
    return recovered


def remove_invalid() -> int:
    """清理 status == invalid 的 Cookie，返回清理数量。"""
    with _LOCK:
        pool = _load()
        before = len(pool.get("cookies", []))
        pool["cookies"] = [c for c in pool.get("cookies", []) if c.get("status") != "invalid"]
        removed = before - len(pool["cookies"])
        if removed:
            _save(pool)
        return removed
