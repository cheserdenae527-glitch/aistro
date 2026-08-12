"""JustOneAPI 客户端 — 拉取小红书蒲公英平台历史粉丝数据。

接口：小红书蒲公英粉丝增长历史 (V1)
  GET /api/xiaohongshu-pgy/api/solar/kol/data/userId/fans_overall_new_history/v1
返回每天的总粉丝数，转成评分引擎可消费的 follower_history 结构。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger("crawler.justoneapi")

CACHE_TTL_SECONDS = 6 * 60 * 60  # 平台数据一天一更，本地缓存 6 小时足够
CN_TZ = timezone(timedelta(hours=8))


def _cn_date_key(value: str) -> str:
    """把任意 ISO 时间转成北京时间日期，用于平台曲线与本地快照按天对齐。"""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CN_TZ)
        return dt.astimezone(CN_TZ).date().isoformat()
    except (ValueError, TypeError):
        return str(value)[:10]


def _cache_dir() -> Path:
    return Path(settings.LOCAL_STORAGE_DIR) / "justoneapi_cache"


def _cache_path(key: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in key)
    return _cache_dir() / f"{safe}.json"


def _cache_read(user_id: str, key: str | None = None) -> dict | None:
    path = _cache_path(key or user_id)
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - payload.get("fetched_at", 0) > CACHE_TTL_SECONDS:
            return None
        return payload.get("data")
    except Exception:
        return None


def _cache_write(user_id: str, data: dict, key: str | None = None) -> None:
    try:
        _cache_dir().mkdir(parents=True, exist_ok=True)
        _cache_path(key or user_id).write_text(
            json.dumps({"fetched_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("JustOneAPI 缓存写入失败 uid=%s: %s", user_id, exc)


def _summarize_platform(history: list[dict], raw_data: dict) -> dict:
    first = history[0]
    last = history[-1]
    start_fans = int(first.get("fans") or 0)
    end_fans = int(last.get("fans") or 0)
    growth_rate = (end_fans - start_fans) / start_fans if start_fans else 0.0
    return {
        "source": "justoneapi",
        "points": len(history),
        "start_fans": start_fans,
        "end_fans": end_fans,
        "fans_increase": end_fans - start_fans,
        "growth_rate": round(growth_rate, 4),
        "start_date": str(first.get("snapshot_at"))[:10],
        "end_date": str(last.get("snapshot_at"))[:10],
        "fans_num_inc": raw_data.get("fansNumInc"),
        "fans_num_inc_rate": raw_data.get("fansNumIncRate"),
    }


def fetch_follower_history(user_id: str, date_type: str = "DAY_90") -> dict:
    """获取平台历史粉丝数据，返回 {"ok", "history", "summary", "error", "cached"}。"""
    token = settings.JUST_ONE_API_TOKEN
    if not token:
        return {"ok": False, "history": [], "summary": None, "error": "未配置 JustOneAPI Token", "cached": False}

    cached = _cache_read(user_id)
    if cached:
        return {
            "ok": True,
            "history": cached.get("history") or [],
            "summary": cached.get("summary"),
            "error": "",
            "cached": True,
        }

    url = (
        settings.JUST_ONE_API_BASE_URL.rstrip("/")
        + "/api/xiaohongshu-pgy/api/solar/kol/data/userId/fans_overall_new_history/v1"
    )
    params = {
        "token": token,
        "userId": user_id,
        "dateType": date_type,
        "increaseType": "FANS_TOTAL",
    }
    timeout = settings.JUST_ONE_API_TIMEOUT_SECONDS
    try:
        resp = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        return {"ok": False, "history": [], "summary": None, "error": str(exc), "cached": False}

    code = body.get("code")
    if code != 0:
        message = body.get("message") or ""
        hint = "Token 无效或余额不足" if code in (100, 600, 601, 602) else "平台暂未收录该博主或接口异常"
        return {
            "ok": False,
            "history": [],
            "summary": None,
            "error": f"JustOneAPI 返回 {code}: {message or hint}",
            "cached": False,
        }

    raw_data = body.get("data") or {}
    raw_list = raw_data.get("list") or []
    history: list[dict] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        date_key = str(item.get("dateKey") or "")
        try:
            fans = int(item.get("num") or 0)
        except (TypeError, ValueError):
            continue
        if not date_key or fans <= 0:
            continue
        history.append(
            {
                "fans": fans,
                "snapshot_at": f"{date_key}T00:00:00+08:00",
                "source": "justoneapi",
            }
        )
    if len(history) < 2:
        return {
            "ok": False,
            "history": [],
            "summary": None,
            "error": "平台粉丝历史数据不足",
            "cached": False,
        }

    summary = _summarize_platform(history, raw_data)
    _cache_write(user_id, {"history": history, "summary": summary})
    return {"ok": True, "history": history, "summary": summary, "error": "", "cached": False}


def merge_follower_history(local_history: list[dict], platform_result: dict) -> list[dict]:
    """合并本地订阅快照与平台历史，平台数据优先，本地按日期补缺。"""
    merged: dict[str, dict] = {}
    for h in local_history or []:
        if not h or not h.get("fans") or not h.get("snapshot_at"):
            continue
        key = _cn_date_key(str(h.get("snapshot_at")))
        merged[key] = {**h, "source": "local"}
    for h in (platform_result.get("history") or []):
        if not h or not h.get("fans") or not h.get("snapshot_at"):
            continue
        key = _cn_date_key(str(h.get("snapshot_at")))
        merged[key] = {**h, "source": "justoneapi"}
    return sorted(merged.values(), key=lambda x: str(x.get("snapshot_at")))


# ---------------------------------------------------------------------------
# 蒲公英补充数据：创作者资料 / 粉丝摘要 / 相似创作者（JustOneAPI 官方接口）
# ---------------------------------------------------------------------------

_PGY_CACHE_PREFIX = "pgy"


def _pgy_cache_key(kind: str, user_id: str, *suffix: str) -> str:
    parts = [_PGY_CACHE_PREFIX, kind, user_id, *map(str, suffix)]
    return "_".join("".join(ch if ch.isalnum() else "_" for ch in part) for part in parts)


def _pgy_get(path: str, params: dict) -> tuple[dict | None, str]:
    """对 JustOneAPI 发 GET，返回 (body, error)。错误码与 fetch_follower_history 保持一致。"""
    token = settings.JUST_ONE_API_TOKEN
    if not token:
        return None, "未配置 JustOneAPI Token"
    url = settings.JUST_ONE_API_BASE_URL.rstrip("/") + path
    try:
        resp = httpx.get(
            url,
            params={"token": token, **params},
            timeout=settings.JUST_ONE_API_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        return None, str(exc)
    code = body.get("code")
    if code != 0:
        message = body.get("message") or ""
        hint = "Token 无效或余额不足" if code in (100, 600, 601, 602) else "平台暂未收录该博主或接口异常"
        return None, f"JustOneAPI 返回 {code}: {message or hint}"
    return body, ""


def fetch_creator_profile(user_id: str) -> dict:
    """蒲公英创作者资料 + 合作报价。返回 {"ok", "data", "error", "cached"}。"""
    cache_key = _pgy_cache_key("creator_profile", user_id)
    cached = _cache_read(user_id, key=cache_key)
    if cached is not None:
        return {"ok": True, "data": cached, "error": "", "cached": True}
    body, err = _pgy_get(
        "/api/xiaohongshu-pgy/api/solar/cooperator/user/blogger/userId/v1",
        {"userId": user_id},
    )
    if err:
        return {"ok": False, "data": None, "error": err, "cached": False}
    data = (body or {}).get("data") or {}
    if not data:
        return {"ok": False, "data": None, "error": "平台暂未收录该博主", "cached": False}
    _cache_write(user_id, data, key=cache_key)
    return {"ok": True, "data": data, "error": "", "cached": False}


def fetch_fans_summary(user_id: str) -> dict:
    """蒲公英粉丝摘要（活跃/互动/阅读/付费粉丝等）。返回 {"ok", "data", "error", "cached"}。"""
    cache_key = _pgy_cache_key("fans_summary", user_id)
    cached = _cache_read(user_id, key=cache_key)
    if cached is not None:
        return {"ok": True, "data": cached, "error": "", "cached": True}
    body, err = _pgy_get(
        "/api/xiaohongshu-pgy/api/solar/kol/dataV3/fansSummary/v1",
        {"userId": user_id},
    )
    if err:
        return {"ok": False, "data": None, "error": err, "cached": False}
    data = (body or {}).get("data") or {}
    if not data:
        return {"ok": False, "data": None, "error": "平台暂未收录该博主", "cached": False}
    _cache_write(user_id, data, key=cache_key)
    return {"ok": True, "data": data, "error": "", "cached": False}


def fetch_similar_kol(user_id: str, page_num: int = 1) -> dict:
    """蒲公英相似创作者分页列表。返回 {"ok", "data", "error", "cached"}，data 含 kols 列表。"""
    cache_key = _pgy_cache_key("similar_kol", user_id, page_num)
    cached = _cache_read(user_id, key=cache_key)
    if cached is not None:
        return {"ok": True, "data": cached, "error": "", "cached": True}
    body, err = _pgy_get(
        "/api/xiaohongshu-pgy/api/solar/kol/get_similar_kol/v1",
        {"userId": user_id, "pageNum": max(1, int(page_num))},
    )
    if err:
        return {"ok": False, "data": None, "error": err, "cached": False}
    data = (body or {}).get("data") or {}
    if not data:
        return {"ok": False, "data": None, "error": "平台暂未收录该博主", "cached": False}
    _cache_write(user_id, data, key=cache_key)
    return {"ok": True, "data": data, "error": "", "cached": False}
