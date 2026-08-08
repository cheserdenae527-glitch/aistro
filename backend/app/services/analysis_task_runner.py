"""博主真实数据分析任务运行器（C9）。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.analysis_task import BloggerAnalysisTask
from app.models.note_detail import NoteDetail
from app.services.blogger_scoring import score_blogger
from crawler.config import load_config
from crawler.gate import gate

logger = logging.getLogger("crawler.analysis_task")

_tasks: dict[str, asyncio.Task] = {}


def _crawler():
    from app.api.v1.notes import _get_crawler

    return _get_crawler(min_delay=0.6, max_delay=1.0, max_retries=1)


def _parse_count(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "").strip().replace(",", "").replace("+", "").replace("＋", "")
    mult = 1
    for unit, factor in (("亿", 100000000), ("万", 10000), ("千", 1000)):
        if unit in s:
            mult = factor
            s = s.replace(unit, "")
            break
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


async def prescreen_user(user_id: str) -> dict:
    """列表粗筛：只读列表数据，不消耗详情请求。"""
    from crawler.processor import normalize_note
    from app.services.xhs_user_resolver import resolve_user_profile

    crawler = _crawler()
    user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    notes_result = await asyncio.to_thread(crawler.get_user_notes, user_url)
    if not notes_result.success:
        err = notes_result.error or ""
        if any(k in err for k in ("Cookie", "失效", "过期")):
            reason = "Cookie 已过期或账号失效，请更新 Cookie"
        else:
            reason = f"获取作品列表失败（{err[:120]}）"
        return {"passed": False, "reason": reason, "fans": 0, "notes": 0, "avg_likes": 0.0}

    raw = notes_result.data or []
    nickname = ""
    for n in raw:
        if not isinstance(n, dict):
            continue
        u = n.get("user") or {}
        if isinstance(u, dict):
            nickname = u.get("nickname") or u.get("nick_name") or u.get("name") or ""
            if nickname:
                break

    profile = await resolve_user_profile(crawler, user_id, nickname=nickname)
    fans = profile.get("fans", 0)
    info_ok = bool(profile.get("ok"))
    info_err = profile.get("error", "")

    likes = []
    for n in raw:
        if not isinstance(n, dict):
            continue
        n.setdefault("id", n.get("note_id", ""))
        norm = normalize_note(n)
        likes.append(norm.get("stats", {}).get("liked", 0))

    cfg = load_config()
    min_follower = int(cfg.get("min_follower_count", 1000))
    min_notes = int(cfg.get("min_note_count", 10))
    min_avg_likes = int(cfg.get("min_avg_likes", 50))
    avg_likes = sum(likes) / len(likes) if likes else 0.0

    reasons = []
    if not info_ok:
        reason = "粉丝数获取失败，请稍后重试或更新 Cookie"
        if info_err and any(k in info_err for k in ("不存在", "NoneType")):
            reason = "账号不存在或粉丝数获取失败"
        elif info_err:
            reason = f"粉丝数获取失败（{info_err[:80]}）"
        reasons.append(reason)
    elif fans < min_follower:
        reasons.append(f"粉丝数不足（{fans} < {min_follower}）")
    if len(raw) < min_notes:
        reasons.append(f"笔记数不足（{len(raw)} < {min_notes}）")
    if avg_likes < min_avg_likes:
        reasons.append(f"列表平均赞不足（{avg_likes:.1f} < {min_avg_likes}）")
    passed = not reasons
    return {
        "passed": passed,
        "reason": "；".join(reasons) if reasons else None,
        "fans": fans,
        "notes": len(raw),
        "avg_likes": round(avg_likes, 1),
    }

async def _get_cached_detail(session, xhs_user_id: str, note_id: str) -> dict | None:
    result = await session.execute(
        select(NoteDetail).where(
            NoteDetail.xhs_user_id == xhs_user_id,
            NoteDetail.platform_note_id == note_id,
        )
    )
    row = result.scalar_one_or_none()
    return row.detail_json if row else None


async def _upsert_detail(session, xhs_user_id: str, note_id: str, detail_json: dict) -> None:
    result = await session.execute(
        select(NoteDetail).where(
            NoteDetail.xhs_user_id == xhs_user_id,
            NoteDetail.platform_note_id == note_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.detail_json = detail_json
        row.fetched_at = datetime.now(timezone.utc)
    else:
        session.add(NoteDetail(xhs_user_id=xhs_user_id, platform_note_id=note_id, detail_json=detail_json))
    await session.flush()


async def _update_task(task_id: uuid.UUID, **fields) -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(BloggerAnalysisTask).where(BloggerAnalysisTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return
        for k, v in fields.items():
            setattr(task, k, v)
        await session.commit()


async def _load_task(task_id: uuid.UUID) -> BloggerAnalysisTask | None:
    async with async_session_factory() as session:
        result = await session.execute(select(BloggerAnalysisTask).where(BloggerAnalysisTask.id == task_id))
        return result.scalar_one_or_none()


async def run_analysis_task(task_id: uuid.UUID) -> None:
    """后台执行分析任务，按批次抓真实详情并评分。"""
    from crawler.processor import normalize_note

    cfg = load_config()
    batch_size = int(cfg.get("analysis_batch_size", 50))
    batch_interval = float(cfg.get("analysis_batch_interval_seconds", 15))
    max_notes = int(cfg.get("analysis_max_notes_per_task", 500))
    timeout_minutes = float(cfg.get("analysis_task_timeout_minutes", 45))

    task = await _load_task(task_id)
    if not task:
        return
    await _update_task(task_id, status="running", started_at=datetime.now(timezone.utc), error=None)

    crawler = _crawler()
    try:
        user_url = f"https://www.xiaohongshu.com/user/profile/{task.xhs_user_id}"
        notes_result = await asyncio.to_thread(crawler.get_user_notes, user_url)
        if not notes_result.success:
            raise RuntimeError(notes_result.error or "获取作品列表失败")
        raw_notes = [n for n in (notes_result.data or []) if isinstance(n, dict)]
        total = len(raw_notes)
        sample_size = min(total, max_notes)
        if sample_size >= 2:
            indices = []
            for i in range(sample_size):
                idx = int(round(i * (total - 1) / (sample_size - 1)))
                if not indices or idx != indices[-1]:
                    indices.append(idx)
        else:
            indices = list(range(sample_size))
        sampled = total > max_notes
        target = len(indices)
        await _update_task(task_id, total_notes=total, target_notes=target)

        real_notes: list[dict] = []
        deadline = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        fetched = 0
        partial = False

        for batch_start in range(0, target, batch_size):
            current_task = await _load_task(task_id)
            if not current_task or current_task.status == "cancelled":
                return
            if datetime.now(timezone.utc) >= deadline:
                partial = True
                break

            batch_positions = indices[batch_start:batch_start + batch_size]
            for pos in batch_positions:
                current_task = await _load_task(task_id)
                if not current_task or current_task.status == "cancelled":
                    return
                if datetime.now(timezone.utc) >= deadline:
                    partial = True
                    break
                n = raw_notes[pos]
                n.setdefault("id", n.get("note_id", ""))
                note_id = n.get("id", "")
                if not note_id:
                    continue
                async with async_session_factory() as session:
                    cached = await _get_cached_detail(session, task.xhs_user_id, note_id)
                    if cached is None:
                        token = n.get("xsec_token", "")
                        if token:
                            from app.api.v1.notes import _extract_detail_items

                            url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_user"
                            detail_result = await asyncio.to_thread(crawler.get_note_detail, url)
                            if detail_result.success and isinstance(detail_result.data, dict):
                                risk_code = detail_result.data.get("code")
                                risk_msg = str(detail_result.data.get("msg") or "")
                                if risk_code in (300011, 300013) or any(k in risk_msg for k in ("频繁", "稍后再试", "账号异常")):
                                    gate.note_failure(risk_msg or str(risk_code))
                                    raise RuntimeError(f"小红书风控限流（{risk_msg or risk_code}），请稍后重试或更新 Cookie")
                            items = _extract_detail_items(detail_result)
                            if items:
                                cached = normalize_note(items[0])
                                cached["full_stats"] = True
                                await _upsert_detail(session, task.xhs_user_id, note_id, cached)
                                await session.commit()
                    if cached is not None:
                        real_notes.append(cached)
                        fetched += 1
                    if fetched % 10 == 0:
                        coverage = fetched / sample_size if sample_size else 0.0
                        await _update_task(task_id, fetched_notes=fetched, coverage=round(coverage, 4))
            if batch_start + batch_size < target and not partial:
                await asyncio.sleep(batch_interval)

        coverage = fetched / sample_size if sample_size else 0.0
        result = score_blogger(real_notes, follower_count=task.follower_count or 0, total_notes=total, sampled=sampled, coverage_denominator=(sample_size if sampled else None))
        status = "partial" if partial else "success"
        await _update_task(
            task_id,
            status=status,
            fetched_notes=fetched,
            coverage=round(coverage, 4),
            confidence=result.get("confidence"),
            result=result,
            finished_at=datetime.now(timezone.utc),
            error=None,
        )
    except Exception as exc:
        logger.exception("分析任务失败 task=%s: %s", task_id, exc)
        await _update_task(task_id, status="failed", error=str(exc), finished_at=datetime.now(timezone.utc))


def start_analysis_task(task_id: uuid.UUID) -> None:
    """在事件循环中调度后台任务并登记引用，便于取消。"""
    loop = asyncio.get_event_loop()
    _tasks[str(task_id)] = loop.create_task(run_analysis_task(task_id))


def cancel_task(task_id: uuid.UUID) -> None:
    t = _tasks.get(str(task_id))
    if t and not t.done():
        t.cancel()
    _tasks.pop(str(task_id), None)

