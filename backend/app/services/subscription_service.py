"""订阅服务 — 供 API 与定时调度复用。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription, SubscriptionSnapshot
from app.services.xhs_runtime import get_xhs_api
from crawler.gate import gate


async def load_follower_history(db: AsyncSession, user_id, xhs_user_id: str) -> list[dict]:
    """读取订阅博主的历史粉丝快照，按时间升序返回，供成长潜力分使用。"""
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.xhs_user_id == xhs_user_id)
    )
    sub = sub_result.scalar_one_or_none()
    if not sub:
        return []
    snap_result = await db.execute(
        select(SubscriptionSnapshot)
        .where(SubscriptionSnapshot.subscription_id == sub.id)
        .order_by(SubscriptionSnapshot.crawled_at)
    )
    return [
        {
            "fans": snap.follower_count,
            "snapshot_at": snap.crawled_at.isoformat() if snap.crawled_at else None,
        }
        for snap in snap_result.scalars().all()
    ]


def _friendly_msg(msg) -> str:
    text = str(msg or "获取失败")
    if "NoneType" in text:
        return "作品接口异常（账号不存在或风控）"
    if "x-rap-param" in text:
        return "小红书风控限流，请稍后重试或更新 Cookie"
    return text


async def _search_user_fallback(api, user_id: str, nickname: str) -> dict:
    """otherinfo 被风控时用昵称搜索兜底，返回粉丝/头像/token。

    优先用搜索返回的 xsec_token 重试 otherinfo；拿不到 token 时直接用搜索里的 fans。
    """
    from app.services.xhs_user_resolver import parse_profile_from_info
    from crawler.processor import _parse_count

    if not nickname:
        return {"ok": False, "fans": None, "nickname": "", "avatar": "", "following": 0, "error": "昵称为空，无法搜索兜底"}
    try:
        success, msg, users = await asyncio.to_thread(api.search_some_user, nickname, 20)
        if not success:
            return {"ok": False, "fans": None, "nickname": "", "avatar": "", "following": 0, "error": str(msg or "用户搜索失败")}
        for u in users or []:
            if not isinstance(u, dict):
                continue
            uid = str(u.get("user_id") or u.get("id") or "")
            if uid != str(user_id):
                continue
            token = str(u.get("xsec_token") or "")
            if token:
                s3, m3, raw3 = await asyncio.to_thread(
                    api.get_user_info, user_id, xsec_token=token, xsec_source="pc_search"
                )
                if s3 and raw3:
                    parsed = parse_profile_from_info(raw3)
                    if parsed["ok"]:
                        return {
                            "ok": True,
                            "fans": parsed["fans"],
                            "nickname": parsed["nickname"] or str(u.get("nickname") or ""),
                            "avatar": parsed["avatar"] or str(u.get("avatar") or u.get("image") or ""),
                            "following": 0,
                            "error": "",
                        }
            fans = _parse_count(u.get("fans") or 0)
            if fans > 0:
                return {
                    "ok": True,
                    "fans": fans,
                    "nickname": str(u.get("nickname") or u.get("name") or ""),
                    "avatar": str(u.get("avatar") or u.get("image") or ""),
                    "following": 0,
                    "error": "",
                }
            break
        return {"ok": False, "fans": None, "nickname": "", "avatar": "", "following": 0, "error": "搜索中未找到该用户"}
    except Exception as exc:
        return {"ok": False, "fans": None, "nickname": "", "avatar": "", "following": 0, "error": str(exc)}

async def refresh_subscription(db: AsyncSession, sub: Subscription) -> dict:
    """刷新单个订阅的粉丝数/笔记数并落快照，返回带 notes 与刷新状态的 payload。"""
    api = await asyncio.to_thread(get_xhs_api)
    from app.schemas.subscription import SubscriptionResponse

    payload = SubscriptionResponse.model_validate(sub).model_dump()
    payload["notes"] = []

    def _failed(error: str) -> dict:
        payload["refresh_status"] = "failed"
        payload["refresh_error"] = error
        return payload

    try:
        await asyncio.to_thread(gate.wait)
    except RuntimeError as exc:
        return _failed(str(exc))

    errors: list[str] = []
    user_ok = False
    profile_note_count = 0

    from app.services.xhs_user_resolver import parse_profile_from_info

    success, msg, raw = await asyncio.to_thread(api.get_user_info, sub.xhs_user_id)
    if not success and gate.is_risk_error(str(msg)):
        gate.note_failure(str(msg))
    if success and raw:
        parsed = parse_profile_from_info(raw)
        if parsed["ok"]:
            user_ok = True
            sub.nickname = parsed["nickname"] or sub.nickname
            sub.avatar = parsed["avatar"] or sub.avatar
            sub.follower_count = parsed["fans"]
        profile_note_count = int(parsed.get("note_count") or 0)
        if profile_note_count:
            sub.note_count = profile_note_count
        else:
            d = raw.get("data", raw) or {}
            for item in d.get("interactions", []) or []:
                if isinstance(item, dict):
                    t = item.get("type", "")
                    try:
                        c = int(item.get("count", 0))
                    except (TypeError, ValueError):
                        c = 0
                    if t == "follows":
                        sub.following_count = c
    if not user_ok:
        fallback = await _search_user_fallback(api, sub.xhs_user_id, sub.nickname or "")
        if fallback["ok"]:
            user_ok = True
            if fallback["fans"] is not None:
                sub.follower_count = fallback["fans"]
            if fallback["following"]:
                sub.following_count = fallback["following"]
            sub.nickname = fallback["nickname"] or sub.nickname
            sub.avatar = fallback["avatar"] or sub.avatar
        else:
            errors.append(f"用户信息：{_friendly_msg(fallback['error'] or msg)}")
    try:
        await asyncio.to_thread(gate.wait)
    except RuntimeError as exc:
        sub.last_crawled_at = datetime.now(timezone.utc)
        db.add(
            SubscriptionSnapshot(
                subscription_id=sub.id,
                note_count=sub.note_count,
                follower_count=sub.follower_count,
                following_count=sub.following_count,
            )
        )
        await db.flush()
        return _failed(str(exc))

    notes_ok = False
    _notes = []
    success2, msg2, notes_data = await asyncio.to_thread(
        api.get_user_all_notes,
        f"https://www.xiaohongshu.com/user/profile/{sub.xhs_user_id}",
        max_notes=50,
    )
    if not success2 and gate.is_risk_error(str(msg2)):
        gate.note_failure(str(msg2))
    if success2:
        notes_ok = True
        if not profile_note_count:
            sub.note_count = len(notes_data or [])
        from crawler.processor import normalize_note

        for n in notes_data or []:
            if not isinstance(n, dict):
                continue
            n.setdefault("id", n.get("note_id", ""))
            _notes.append(normalize_note(n))
    else:
        errors.append(f"笔记数：{_friendly_msg(msg2)}")

    sub.last_crawled_at = datetime.now(timezone.utc)
    db.add(
        SubscriptionSnapshot(
            subscription_id=sub.id,
            note_count=sub.note_count,
            follower_count=sub.follower_count,
            following_count=sub.following_count,
        )
    )
    await db.flush()

    payload = SubscriptionResponse.model_validate(sub).model_dump()
    payload["notes"] = _notes[:50]
    if _notes:
        try:
            from app.services.knowledge_base import sync_notes
            await sync_notes(db, sub.user_id, _notes, source="subscription")
            await db.flush()
        except Exception as exc:
            errors.append(f"知识库：{_friendly_msg(str(exc))}")
    if not user_ok and not notes_ok:
        payload["refresh_status"] = "failed"
        payload["refresh_error"] = "；".join(errors) or "刷新失败"
    elif errors:
        payload["refresh_status"] = "partial"
        payload["refresh_error"] = "；".join(errors)
    else:
        payload["refresh_status"] = "ok"
        payload["refresh_error"] = None
    return payload


