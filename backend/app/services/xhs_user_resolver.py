"""博主主页信息解析 — otherinfo 优先，昵称搜索兜底。

小红书 `otherinfo` 接口在未携带用户主页 xsec_token 时经常返回 300011
（"账号异常，请稍后重试"），但按昵称搜索用户接口可以返回同一账号的
fans / note_count / xsec_token。本模块把两层策略封装成一个入口，
供粗筛、分析任务和订阅刷新复用。
"""
from __future__ import annotations

import asyncio
import logging

from crawler.processor import _parse_count

logger = logging.getLogger("crawler.xhs_user")

_PROFILE_COUNT_KEYS = ("fans", "fans_total", "follower_count")


def parse_profile_from_info(raw: dict) -> dict:
    """从 otherinfo 原始响应解析博主资料。

    返回 {"ok", "fans", "nickname", "avatar"}；ok 表示粉丝数解析成功。
    """
    fans = 0
    nickname = ""
    avatar = ""
    try:
        if not isinstance(raw, dict):
            return {"ok": False, "fans": 0, "nickname": "", "avatar": ""}
        d = raw.get("data", raw) or {}
        if not isinstance(d, dict):
            return {"ok": False, "fans": 0, "nickname": "", "avatar": ""}
        bi = d.get("basic_info") or {}
        if isinstance(bi, dict):
            for key in _PROFILE_COUNT_KEYS:
                if bi.get(key) not in (None, ""):
                    fans = _parse_count(bi.get(key))
                    break
            nickname = bi.get("nickname") or bi.get("nick_name") or ""
            avatar = bi.get("imageb") or bi.get("images") or ""
            if isinstance(avatar, list):
                avatar = avatar[0] if avatar else ""
        for item in d.get("interactions") or []:
            if isinstance(item, dict) and item.get("type") == "fans":
                count = item.get("count")
                if count not in (None, ""):
                    fans = _parse_count(count)
                    break
    except Exception as exc:
        logger.debug("解析 otherinfo 失败: %s", exc)
    return {"ok": fans > 0, "fans": fans, "nickname": nickname, "avatar": avatar}


def _user_id_of(item: dict) -> str:
    return str(item.get("user_id") or item.get("id") or "")


def _nickname_of(item: dict) -> str:
    return item.get("nickname") or item.get("nick_name") or item.get("name") or ""


async def _fetch_profile(
    crawler,
    user_id: str,
    xsec_token: str = "",
    xsec_source: str = "pc_search",
    tries: int = 2,
) -> dict:
    """调 otherinfo；拿不到粉丝数时视为失败并返回最后一次错误。"""
    last_err = ""
    for _ in range(tries):
        result = await asyncio.to_thread(
            crawler.get_user_info,
            user_id,
            xsec_token=xsec_token,
            xsec_source=xsec_source,
        )
        if result.success and isinstance(result.data, dict):
            parsed = parse_profile_from_info(result.data)
            if parsed["ok"]:
                return {**parsed, "xsec_token": xsec_token, "error": ""}
            last_err = "用户信息为空"
        else:
            last_err = str(result.error or "") or "用户信息获取失败"
        await asyncio.sleep(1.5)
    return {
        "ok": False,
        "fans": 0,
        "nickname": "",
        "avatar": "",
        "xsec_token": xsec_token,
        "error": last_err,
    }


async def _nickname_from_notes(crawler, user_id: str) -> str:
    try:
        url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        notes = await asyncio.to_thread(crawler.get_user_notes, url)
        if notes.success:
            for n in notes.data or []:
                if not isinstance(n, dict):
                    continue
                u = n.get("user") or {}
                if isinstance(u, dict) and _nickname_of(u):
                    return _nickname_of(u)
    except Exception as exc:
        logger.debug("作品列表取昵称失败: %s", exc)
    return ""


async def resolve_user_profile(crawler, user_id: str, nickname: str = "") -> dict:
    """获取博主主页资料，返回：
    {"ok", "fans", "nickname", "avatar", "note_count", "xsec_token", "error"}
    """
    profile = await _fetch_profile(crawler, user_id)
    note_count = 0
    if not nickname:
        nickname = await _nickname_from_notes(crawler, user_id)
    if profile["ok"]:
        return {
            **profile,
            "nickname": profile["nickname"] or nickname,
            "note_count": note_count,
            "error": "",
        }
    if nickname:
        try:
            search = await asyncio.to_thread(crawler.search_users, nickname, 20)
            if search.success:
                for item in search.data or []:
                    if not isinstance(item, dict) or _user_id_of(item) != str(user_id):
                        continue
                    fans = _parse_count(item.get("fans") or 0)
                    note_count = _parse_count(item.get("note_count") or item.get("notes") or 0)
                    token = str(item.get("xsec_token") or "")
                    if token:
                        retry = await _fetch_profile(
                            crawler, user_id, xsec_token=token, tries=1
                        )
                        if retry["ok"]:
                            return {
                                **retry,
                                "nickname": retry["nickname"] or _nickname_of(item) or nickname,
                                "note_count": note_count,
                                "error": "",
                            }
                    if fans > 0:
                        return {
                            "ok": True,
                            "fans": fans,
                            "nickname": _nickname_of(item) or nickname,
                            "avatar": str(item.get("avatar") or item.get("image") or ""),
                            "note_count": note_count,
                            "xsec_token": token,
                            "error": "",
                        }
                    break
        except Exception as exc:
            logger.debug("搜索兜底失败: %s", exc)
    return {
        **profile,
        "nickname": nickname,
        "note_count": note_count,
        "error": profile["error"] or "粉丝数获取失败",
    }
