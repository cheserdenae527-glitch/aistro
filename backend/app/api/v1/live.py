"""直播工坊模块 API — 项目/形象/脚本/弹幕配置/场次/复盘 CRUD + AI 生成 + 合规 + 开播包导出。

鉴权边界（SPEC §6）：
- live-projects / scripts / danmaku / sessions / metrics / review：JWT + shop 所有权
  （project -> shop -> merchant -> user，跨用户一律 404）
- live-avatars：org 归属校验（MVP 退化 org_id = 创建用户主账号 users.id，
  见 SPEC §4/§10 与 app/models/live_avatar.py 注释），跨 org 一律 404
- 凡接受 avatar_id 入参的接口（scripts/generate、sessions 创建/PATCH）都校验
  该形象的 org_id 与当前用户一致，跨 org 一律 404

频控（成功才计入）：
- scripts/generate、danmaku-config/generate：60s，key = user+shop，独立 key
- sessions/{sid}/review：30s，key = user+session_id
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import os
import pickle
import socket
import subprocess
import time
import uuid
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Any

import httpx

import openai
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.live_compliance import LiveCompliance, default_wordlist
from app.ai.live_danmaku_agent import LiveDanmakuAgent, LiveDanmakuAgentError
from app.ai.live_review_agent import LiveReviewAgent, LiveReviewAgentError
from app.ai.live_script_agent import LiveScriptAgent, LiveScriptAgentError
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import peek_rate_limit, set_rate_limit
from app.ai.doubao_image import ImageGenError, generate_avatar as doubao_generate_avatar
from app.services.storage import get_presigned_url, upload_bytes, upload_fileobj
from app.models.live_avatar import LiveAvatar
from app.models.live_danmaku_config import LiveDanmakuConfig
from app.models.live_project import LiveProject
from app.models.live_script import LiveScript
from app.models.live_session import LiveSession
from app.models.live_session_metric import LiveSessionMetric
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.user import User
from app.schemas.live import (
    AiGenerateImageRequest,
    EngineAvatarCreateRequest,
    EngineTestRequest,
    EngineTestResult,

    ComplianceCheckRequest,
    ComplianceResult,
    DanmakuConfigUpdate,
    LiveAvatarCreate,
    LiveAvatarListResponse,
    LiveAvatarOut,
    LiveAvatarUpdate,
    LiveDanmakuConfigOut,
    LiveExportBundle,
    LiveProjectCreate,
    LiveProjectListResponse,
    LiveProjectOut,
    LiveProjectUpdate,
    LiveScriptOut,
    LiveSessionCreate,
    LiveSessionListResponse,
    LiveSessionMetricOut,
    LiveSessionOut,
    LiveSessionUpdate,
    MetricsCreate,
    ReviewResponse,
    ScriptGenerateRequest,
    ScriptUpdateRequest,
)

router = APIRouter(tags=["live"])

_RATE_TTL_SCRIPTS = 60
_RATE_TTL_DANMAKU = 60
_RATE_TTL_REVIEW = 30
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_DEFAULT_AI_LABEL = "本直播间由 AI 数字人出镜，真人运营团队值守"
_ENGINE_SENSITIVE_KEYS = ("api_key", "secret")
_ENGINE_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_ENGINE_LOOPBACK_PORT = 8010
_MAX_ENGINE_AVATAR_DIRS = 20
_MAX_WATCH_TASKS = 10
_WATCH_TASKS: set[asyncio.Task] = set()


def _validate_engine_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("引擎地址需以 http:// 或 https:// 开头")
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if host not in _LOOPBACK_HOSTS or port != _ENGINE_LOOPBACK_PORT:
        raise ValueError("引擎地址仅允许本机 8010 回环地址")
    return value.rstrip("/")


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _validate_media_url_host(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("素材地址需以 http:// 或 https:// 开头")
    host = (parsed.hostname or "").lower()
    parsed_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    minio_parsed = urlparse(settings.MINIO_ENDPOINT)
    minio_host = (minio_parsed.hostname or "").lower()
    minio_port = minio_parsed.port or 9000
    media_parsed = urlparse(settings.PUBLIC_BASE_URL)
    media_port = media_parsed.port or (443 if media_parsed.scheme == "https" else 80)
    if host in _LOOPBACK_HOSTS:
        if parsed_port not in (minio_port, media_port):
            raise ValueError("素材地址仅允许本机媒体服务回环端口")
        return value
    if minio_host and host == minio_host:
        return value
    try:
        infos = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return value
    for info in infos:
        if _is_private_ip(str(info[4][0])):
            raise ValueError("素材地址指向内网或保留地址")
    return value


async def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user

_PLATFORM_NAMES = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "wechat": "视频号（微信）",
}

_TYPE_LABELS = {
    "opening": "开场留人",
    "product": "产品介绍",
    "promo": "优惠逼单",
    "interaction": "互动",
    "qa": "答疑",
    "closing": "收尾",
}

_DEFAULT_PERSONA = {
    "name": "门店主播",
    "personality": "亲切热情，懂美食",
    "style": "烟火气，口语化",
    "knowledge_scope": "本店菜品、优惠、营业信息",
    "forbidden_topics": ["政治", "宗教"],
}


# ============================================================
# 鉴权与资源 helper
# ============================================================


async def _get_shop(shop_id: str, user: User, db: AsyncSession) -> Shop:
    try:
        shop_uuid = uuid.UUID(shop_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Shop not found")
    result = await db.execute(
        select(Shop)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Shop.id == shop_uuid, Merchant.user_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def _get_project(project_id: str, user: User, db: AsyncSession) -> LiveProject:
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(LiveProject)
        .join(Shop, LiveProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(LiveProject.id == project_uuid, Merchant.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_avatar(avatar_id: str, user: User, db: AsyncSession) -> LiveAvatar:
    """按 org 归属取形象；跨 org 一律 404。"""
    try:
        avatar_uuid = uuid.UUID(avatar_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return await _get_avatar_by_uuid(avatar_uuid, user, db)


async def _get_avatar_by_uuid(
    avatar_id: uuid.UUID, user: User, db: AsyncSession
) -> LiveAvatar:
    result = await db.execute(
        select(LiveAvatar).where(
            LiveAvatar.id == avatar_id, LiveAvatar.org_id == user.id
        )
    )
    avatar = result.scalar_one_or_none()
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar


async def _get_script(
    project: LiveProject, script_id: str, db: AsyncSession
) -> LiveScript:
    try:
        script_uuid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Script not found")
    result = await db.execute(
        select(LiveScript).where(
            LiveScript.id == script_uuid, LiveScript.project_id == project.id
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


async def _get_session(
    project: LiveProject, session_id: str, db: AsyncSession
) -> LiveSession:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(LiveSession).where(
            LiveSession.id == session_uuid, LiveSession.project_id == project.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _validate_operator(operator_id: uuid.UUID, db: AsyncSession) -> None:
    user = await db.get(User, operator_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Operator not found")


async def _active_confirmed_script(
    project_id: uuid.UUID, db: AsyncSession
) -> LiveScript | None:
    result = await db.execute(
        select(LiveScript)
        .where(
            LiveScript.project_id == project_id,
            LiveScript.is_archived.is_(False),
            LiveScript.status == "confirmed",
        )
        .order_by(LiveScript.generation_batch.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_script(project_id: uuid.UUID, db: AsyncSession) -> LiveScript | None:
    result = await db.execute(
        select(LiveScript)
        .where(LiveScript.project_id == project_id)
        .order_by(LiveScript.generation_batch.desc(), LiveScript.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _mask_engine_config(cfg: dict | None) -> dict | None:
    """engine_config GET 脱敏：api_key 等敏感字段不原样回传，仅返回是否已配置。"""
    if not cfg:
        return None
    masked: dict[str, Any] = {}
    for k, v in cfg.items():
        if k in _ENGINE_SENSITIVE_KEYS:
            continue
        masked[k] = v
    masked["api_key_configured"] = bool(cfg.get("api_key"))
    return masked


def _project_payload(project: LiveProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "shop_id": project.shop_id,
        "title": project.title,
        "platform": project.platform,
        "goal": project.goal,
        "promo_items": project.promo_items,
        "ai_label_text": project.ai_label_text,
        "engine_config": _mask_engine_config(project.engine_config),
        "status": project.status,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _build_script_markdown(script: LiveScript) -> str:
    lines = [f"# {script.title}", ""]
    for seg in script.content or []:
        seg_type = str(seg.get("type", ""))
        title = str(seg.get("title") or _TYPE_LABELS.get(seg_type, seg_type))
        duration = seg.get("duration_sec", "?")
        lines.append(f"## {title}（{duration}s）")
        lines.append(str(seg.get("text", "")))
        cue = seg.get("cue")
        if cue:
            lines.append("")
            lines.append(f"[画面/动作提示] {cue}")
        lines.append("")
    lines.append(f"总时长：{script.total_duration_sec}s" if script.total_duration_sec else "")
    return "\n".join(lines).rstrip() + "\n"


def _build_engine_guide(project: LiveProject, ai_label_text: str) -> str:
    platform = _PLATFORM_NAMES.get(project.platform, project.platform)
    lines = [
        "1. 本地启动 LiveTalking（数字人视频实时生成），通过 RTMP 推流到 " + platform + "。",
        "2. 将 persona.json 与 wordlist.txt 导入 digital-human-livestream 管理后台"
        "（/admin/persona、/admin/wordlist），热加载生效。",
        "3. 弹幕互动：" + platform + " 不在 MVP 自动弹幕范围，请使用导出包 reply_rules 的"
        "候选话术在直播间人工粘贴。",
        f"4. AI 标识提醒：直播须展示 AI 标识文案「{ai_label_text}」，开播前由值守人确认。",
        "5. LiveTalking 水印提醒：发布到 B站/视频号/抖音的视频需带 LiveTalking 水印与标识，"
        "与 AI 标识合规要求一致。",
        "6. 平台数字人直播规则随时更新，以平台最新公告为准。",
    ]
    if project.engine_config and project.engine_config.get("base_url"):
        lines.append(f"7. 本地引擎管理后台地址：{project.engine_config['base_url']}")
    return "\n".join(lines)


def _normalize_persona_for_engine(persona: dict) -> dict:
    """将人设补充为引擎可读格式（digital-human-livestream config/persona.json）。

    live_avatars.persona / 弹幕配置可能使用 avatar 风格字段
    {identity, tone, boundaries, forbidden_topics}，而引擎只认
    {name, personality, style, knowledge_scope, forbidden_topics} 且四者均必填非空。

    策略：
    1. 保留原字段不丢信息（identity/tone/boundaries 仍保留）；
    2. 映射补充 name(identity)、style(tone)；
    3. 补齐引擎四必填字段（缺 personality/knowledge_scope/name/style 时给合理兜底），
       保证开播包与 engine-test 推送可直接被 digital-human-livestream 接受。
    """
    persona = dict(persona or {})
    for src, dst in (("identity", "name"), ("tone", "style")):
        value = persona.get(src)
        if value and dst not in persona:
            persona[dst] = value
    defaults = {
        "name": "门店主播",
        "personality": "亲切热情，自然大方",
        "style": "烟火气，口语化",
        "knowledge_scope": "本店菜品、优惠与营业信息",
    }
    for key, fallback in defaults.items():
        value = persona.get(key)
        if not isinstance(value, str) or not value.strip():
            persona[key] = fallback
    return persona


# ============================================================
# 直播项目
# ============================================================


@router.post("/live-projects", response_model=LiveProjectOut)
async def create_project(
    body: LiveProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _get_shop(str(body.shop_id), current_user, db)
    project = LiveProject(
        shop_id=shop.id,
        title=body.title,
        platform=body.platform,
        goal=body.goal,
        promo_items=body.promo_items,
        ai_label_text=body.ai_label_text,
        engine_config=body.engine_config,
        status="draft",
    )
    db.add(project)
    await db.flush()
    return _project_payload(project)


@router.get("/live-projects", response_model=LiveProjectListResponse)
async def list_projects(
    shop_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = (
        select(LiveProject)
        .join(Shop, LiveProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Merchant.user_id == current_user.id)
    )
    if shop_id is not None:
        base = base.where(LiveProject.shop_id == shop_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(LiveProject.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return LiveProjectListResponse(
        items=[_project_payload(p) for p in rows], total=total, page=page, size=page_size
    )


@router.get("/live-projects/{project_id}", response_model=LiveProjectOut)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    return _project_payload(project)


@router.patch("/live-projects/{project_id}", response_model=LiveProjectOut)
async def update_project(
    project_id: str,
    body: LiveProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    return _project_payload(project)


@router.delete("/live-projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    await db.delete(project)
    await db.flush()
    return {"ok": True}




def _trim_engine_body(text: str, limit: int = 200) -> str:
    """截断引擎响应正文，避免把超长 HTML 塞进报错/报告。"""
    text = (text or "").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text or ""


def _engine_exc_text(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "连接超时（15s）"
    if isinstance(exc, httpx.ConnectError):
        return f"无法连接（{exc.__class__.__name__}）"
    return f"{exc.__class__.__name__}: {exc}"


async def _engine_push(
    client: httpx.AsyncClient,
    url: str,
    payload: Any,
    headers: dict[str, str],
    label: str,
) -> dict:
    """POST JSON 到引擎管理后台 API。

    - 2xx → ok
    - 404 → skipped（纯 LiveTalking 无 /admin 管理后台，不阻断）
    - 其他失败 → failed（调用方决定是否整体失败）
    """
    try:
        resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        return {"status": "failed", "detail": f"请求失败：{_engine_exc_text(exc)}"}
    if resp.status_code == 404:
        return {
            "status": "skipped",
            "detail": f"引擎未提供 {label} 接口（HTTP 404），可能为纯 LiveTalking，已跳过配置推送",
        }
    if resp.status_code >= 400:
        return {
            "status": "failed",
            "detail": f"HTTP {resp.status_code}：{_trim_engine_body(resp.text)}",
        }
    return {"status": "ok", "detail": _trim_engine_body(resp.text) or "ok"}


@router.post(
    "/live-projects/{project_id}/engine-test",
    response_model=EngineTestResult,
)
async def test_engine_connection(
    project_id: str,
    body: EngineTestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本地引擎「连接测试」：GET {base_url}/health 健康检查 + 可选 persona/wordlist 配置推送。

    - 未配置 base_url → 400
    - 健康检查失败 / 配置推送失败（非 404）→ 502，且不更新 last_health_check
    - 引擎未提供 /admin API（404）→ 推送标记 skipped，不阻断（纯 LiveTalking 场景）
    - 通过后写回 engine_config.last_health_check（UTC ISO）
    """
    project = await _get_project(project_id, current_user, db)
    cfg = dict(project.engine_config or {})
    # 允许请求体覆盖 base_url（前端测试未保存的表单地址）
    override_url = (body.base_url or "").strip().rstrip("/") if body and body.base_url else ""
    base_url = override_url or str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(
            status_code=400, detail="未配置本地引擎管理后台地址（engine_config.base_url）"
        )
    try:
        base_url = _validate_engine_base_url(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    headers = {}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    push_persona = body.push_persona if body is not None else True
    push_wordlist = body.push_wordlist if body is not None else True

    # 与开播包导出同款优先级解析 persona / wordlist
    persona_json: dict | None = body.persona_json if body and body.persona_json else None
    wordlist: list[str] | None = body.wordlist if body and body.wordlist else None
    danmaku: LiveDanmakuConfig | None = None
    if persona_json is None or wordlist is None:
        danmaku = (
            await db.execute(
                select(LiveDanmakuConfig).where(
                    LiveDanmakuConfig.project_id == project.id
                )
            )
        ).scalar_one_or_none()
    if persona_json is None:
        if danmaku and danmaku.persona:
            persona_json = dict(danmaku.persona)
        else:
            script = await _active_confirmed_script(project.id, db)
            persona_json = (
                dict(script.persona_snapshot) if script and script.persona_snapshot else dict(_DEFAULT_PERSONA)
            )
    if wordlist is None:
        wordlist = (
            list(danmaku.sensitive_words)
            if danmaku and danmaku.sensitive_words
            else default_wordlist()
        )
    persona_json = _normalize_persona_for_engine(persona_json)

    health: dict | None = None
    persona_push: dict | None = None
    wordlist_push: dict | None = None
    async with httpx.AsyncClient(timeout=_ENGINE_TIMEOUT) as client:
        t0 = time.perf_counter()
        try:
            resp = await client.get(f"{base_url}/health", headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"引擎健康检查失败：{_engine_exc_text(exc)}"
            )
        latency_ms = round((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"引擎健康检查未通过（HTTP {resp.status_code}）："
                    f"{_trim_engine_body(resp.text)}"
                ),
            )
        health = {
            "ok": True,
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "detail": _trim_engine_body(resp.text) or "ok",
        }

        if push_persona:
            persona_push = await _engine_push(
                client, f"{base_url}/admin/persona", persona_json, headers, "/admin/persona"
            )
            if persona_push["status"] == "failed":
                raise HTTPException(
                    status_code=502, detail=f"人设推送失败：{persona_push['detail']}"
                )
        if push_wordlist:
            # digital-human-livestream 真实接口：POST /admin/wordlist 接受
            # {"content": "每行一词\nregex:xxx"}（README 示例与实现不一致，以实现为准）
            wordlist_push = await _engine_push(
                client,
                f"{base_url}/admin/wordlist",
                {"content": "\n".join(wordlist)},
                headers,
                "/admin/wordlist",
            )
            if wordlist_push["status"] == "failed":
                raise HTTPException(
                    status_code=502, detail=f"敏感词推送失败：{wordlist_push['detail']}"
                )

    now_iso = datetime.now(timezone.utc).isoformat()
    # 仅当测试的是项目已保存的 base_url 才写回 last_health_check；
    # override 地址未保存，不污染项目配置（返回值仍带本次检查时间）。
    if not override_url:
        cfg["last_health_check"] = now_iso
        project.engine_config = cfg
        await db.flush()
    return EngineTestResult(
        ok=True,
        base_url=base_url,
        health=health,
        persona_push=persona_push,
        wordlist_push=wordlist_push,
        last_health_check=now_iso,
    )

# ============================================================
# 数字人形象（org 维度，团队级共享）
# ============================================================


_AVATAR_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_AVATAR_IMAGE_MIME = ("image/png", "image/jpeg", "image/webp")
_AVATAR_VIDEO_MAX_BYTES = 200 * 1024 * 1024  # 200MB
_AVATAR_VIDEO_MIME = ("video/mp4", "video/webm", "video/quicktime")


@router.post("/live-avatars/upload-image")
async def upload_avatar_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传形象图到 MinIO，返回可访问 URL（形象表单 image_url 使用）。

    与 live-avatars 一致为登录用户维度；图片 ≤10MB 且为 PNG/JPEG/WebP。
    返回的 url 为带签名链接（7 天），object_name 为 MinIO 对象路径。
    """
    data = await file.read()
    if len(data) > _AVATAR_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="形象图超过 10MB")
    mime = (file.content_type or "").lower()
    if mime not in _AVATAR_IMAGE_MIME:
        raise HTTPException(status_code=400, detail="仅支持 PNG/JPEG/WebP 图片")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的图片格式")
    object_name = upload_bytes(data, mime, folder="live_avatars")
    return {
        "url": get_presigned_url(object_name, expires=7 * 24 * 3600),
        "object_name": object_name,
    }


@router.post("/live-avatars/upload-video")
async def upload_avatar_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传驱动视频到 MinIO，返回可访问 URL（形象表单 video_url 使用）。

    与 live-avatars 一致为登录用户维度；视频 ≤200MB 且为 MP4/WebM/MOV。
    """
    from tempfile import SpooledTemporaryFile

    mime = (file.content_type or "").lower()
    if mime not in _AVATAR_VIDEO_MIME:
        raise HTTPException(status_code=400, detail="仅支持 MP4/WebM/MOV 视频")
    size = 0
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > _AVATAR_VIDEO_MAX_BYTES:
                raise HTTPException(status_code=400, detail="驱动视频超过 200MB")
            tmp.write(chunk)
        object_name = upload_fileobj(tmp, mime, folder="live_avatars")
    return {
        "url": get_presigned_url(object_name, expires=7 * 24 * 3600),
        "object_name": object_name,
    }


@router.post("/live-avatars/{avatar_id}/engine-avatar")
async def create_engine_avatar(
    avatar_id: str,
    body: EngineAvatarCreateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把形象驱动视频提交到引擎 Avatar 生成 API（LiveTalking /api/avatar/task）。

    - video_url 必填（引擎抽帧生成形象）；引擎地址取 body 覆盖或形象已存 engine_base_url
    - 提交后引擎异步生成 data/avatars/<engine_avatar_id>，轮询
      GET /live-avatars/{id}/engine-avatar/status 查进度
    - 生成成功后在引擎用 --avatar_id <engine_avatar_id> 启动
    """
    avatar = await _get_avatar(avatar_id, current_user, db)
    video_url = (avatar.video_url or "").strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="请先上传或填写驱动视频（video_url）")
    override = (body.engine_base_url or "").strip().rstrip("/") if body and body.engine_base_url else ""
    engine_base = override or (avatar.engine_base_url or "").strip().rstrip("/")
    if not engine_base:
        raise HTTPException(status_code=400, detail="请填写引擎管理后台地址（engine_base_url）")
    try:
        video_url = await asyncio.to_thread(_validate_media_url_host, video_url)
        engine_base = _validate_engine_base_url(engine_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    engine_avatar_id = f"airestro_{uuid.uuid4().hex[:12]}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            vr = await client.get(video_url)
            vr.raise_for_status()
            video_bytes = vr.content
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"下载驱动视频失败：{_engine_exc_text(exc)}")
    # 达标检查 + 预处理（转 720x960 竖版 + 提亮），避免引擎卡在 40% 人脸检测
    try:
        prepared, mime = _prepare_engine_video(video_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"驱动视频不达标：{exc}")
    # 确保引擎在线（不在线自动启动并等待）
    if not await _ensure_engine_online(engine_base):
        raise HTTPException(
            status_code=502,
            detail="引擎不在线且自动启动失败，请先点「启动引擎」或检查引擎配置",
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            resp = await client.post(
                f"{engine_base}/api/avatar/task",
                data={"model": "wav2lip", "avatar_id": engine_avatar_id},
                files={"video_file": (f"{engine_avatar_id}.mp4", prepared, mime)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"连接引擎失败：{_engine_exc_text(exc)}")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"引擎创建形象任务失败（HTTP {resp.status_code}）：{_trim_engine_body(resp.text)}",
        )
    try:
        payload = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="引擎返回无法解析的响应")
    if payload.get("code", 0) != 0:
        raise HTTPException(
            status_code=502, detail=f"引擎创建形象任务失败：{payload.get('msg') or '未知错误'}"
        )
    task_id = str((payload.get("data") or {}).get("task_id") or "")
    if not task_id:
        raise HTTPException(status_code=502, detail="引擎未返回 task_id")
    avatar.engine_base_url = engine_base
    avatar.engine_avatar_id = engine_avatar_id
    avatar.engine_task_id = task_id
    await db.flush()
    # 后台监控：完成后自动重启引擎用新形象（不依赖前端轮询）
    if len(_WATCH_TASKS) >= _MAX_WATCH_TASKS:
        raise HTTPException(status_code=429, detail="后台引擎任务过多，请稍后再试")
    task = asyncio.create_task(
        _safe_watch_engine_avatar_task(task_id, engine_base, engine_avatar_id)
    )
    _WATCH_TASKS.add(task)
    task.add_done_callback(_WATCH_TASKS.discard)
    return {"task_id": task_id, "avatar_id": engine_avatar_id}


@router.get("/live-avatars/{avatar_id}/engine-avatar/status")
async def get_engine_avatar_status(
    avatar_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询引擎 Avatar 生成任务进度（GET /api/avatar/task/{task_id}）。"""
    avatar = await _get_avatar(avatar_id, current_user, db)
    engine_base = (avatar.engine_base_url or "").strip().rstrip("/")
    task_id = (avatar.engine_task_id or "").strip()
    if not engine_base or not task_id:
        return {
            "status": "idle",
            "progress": 0,
            "engine_avatar_id": avatar.engine_avatar_id,
            "error_msg": "",
        }
    try:
        engine_base = _validate_engine_base_url(engine_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.get(f"{engine_base}/api/avatar/task/{task_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"连接引擎失败：{_engine_exc_text(exc)}")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"引擎查询任务失败（HTTP {resp.status_code}）：{_trim_engine_body(resp.text)}",
        )
    try:
        payload = resp.json()
        data = payload.get("data") or {}
    except Exception:
        raise HTTPException(status_code=502, detail="引擎返回无法解析的响应")
    status = str(data.get("status") or "unknown")
    try:
        progress = int(data.get("progress") or 0)
    except (TypeError, ValueError):
        progress = 0
    restarted = False
    if status == "completed" and avatar.engine_avatar_id:
        # 生成完成 → 自动重启引擎用新形象（幂等：已在用则跳过）
        restarted = _restart_live_engine(avatar.engine_avatar_id)
    elif status == "failed":
        # 生成失败 → 重启引擎清理可能的卡死任务显存
        if avatar.engine_avatar_id:
            _restart_live_engine(avatar.engine_avatar_id)
        else:
            _restart_live_engine("wav2lip_avatar_female_model")
    return {
        "status": status,
        "progress": max(0, min(100, progress)),
        "engine_avatar_id": avatar.engine_avatar_id,
        "error_msg": str(data.get("error_msg") or ""),
        "restarted": restarted,
    }


@router.post("/live-avatars/ai-generate-image")
async def ai_generate_avatar_image(
    body: AiGenerateImageRequest,
    current_user: User = Depends(get_current_user),
):
    """用 AI（豆包 Seedream）按用户自定义描述生成数字人形象图，存 MinIO 后返回 4 张候选。

    供形象表单「AI 生成形象」使用：用户输入风格描述（性别/年龄/职业/风格等）定义具体形象。
    """
    try:
        results = await doubao_generate_avatar(body.prompt)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成形象失败：{exc}")
    options = []
    for data, mime in results:
        object_name = upload_bytes(data, mime or "image/png", folder="live_avatars")
        options.append(
            {
                "url": get_presigned_url(object_name, expires=7 * 24 * 3600),
                "object_name": object_name,
            }
        )
    return {"items": options}


def _build_static_avatar(img_bytes: bytes, workdir: str, avatar_id: str) -> str:
    """把单张形象图生成为 wav2lip 静态形象（full_imgs/face_imgs/coords.pkl）。

    竖版 3:4（720x960）、300 帧静态循环；haar 检测人脸 → face_imgs 256x256（wav2lip256 要求）。
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(img_bytes, np.uint8)
    src = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if src is None:
        raise ValueError("无法解析形象图")
    h, w = src.shape[:2]
    th = h
    tw = int(th * 3 / 4)
    if tw > w:
        tw = w
        th = int(w * 4 / 3)
    x0 = max(0, (w - tw) // 2)
    img = cv2.resize(src[:, x0 : x0 + tw], (720, 960))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces):
        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    else:
        fw = int(img.shape[1] * 0.6)
        fh = int(fw * 1.15)
        fx = (img.shape[1] - fw) // 2
        fy = int(img.shape[0] * 0.18)
    x1, y1 = fx, fy
    x2, y2 = min(img.shape[1], fx + fw), min(img.shape[0], fy + fh + 10)
    base = os.path.join(workdir, "data", "avatars", avatar_id)
    os.makedirs(os.path.join(base, "full_imgs"), exist_ok=True)
    os.makedirs(os.path.join(base, "face_imgs"), exist_ok=True)
    face256 = cv2.resize(img[y1:y2, x1:x2], (256, 256))
    coord = (int(y1), int(y2), int(x1), int(x2))
    coords = []
    for i in range(300):
        cv2.imwrite(f"{base}/full_imgs/{i:08d}.png", img)
        cv2.imwrite(f"{base}/face_imgs/{i:08d}.png", face256)
        coords.append(coord)
    with open(os.path.join(base, "coords.pkl"), "wb") as f:
        pickle.dump(coords, f)
    return base


def _build_dynamic_avatar(video_bytes: bytes, workdir: str, avatar_id: str) -> str:
    """把驱动视频生成为 wav2lip 动态形象（每帧抽帧 + 每帧人脸坐标）。

    目标 720x960（3:4 竖版）：视频帧按中心裁剪到 3:4 再缩放；逐帧 haar 检测人脸，
    检测不到时沿用上一帧坐标保持稳定。最多 300 帧。
    """
    import cv2

    def _to_vertical(frame):
        h, w = frame.shape[:2]
        if w / h > 3 / 4:
            tw = int(h * 3 / 4)
            x0 = (w - tw) // 2
            frame = frame[:, x0 : x0 + tw]
        else:
            th = int(w * 4 / 3)
            y0 = int((h - th) * 0.35)  # 偏上取景，保脸
            y0 = max(0, min(y0, h - th))
            frame = frame[y0 : y0 + th, :]
        return cv2.resize(frame, (720, 960))

    import tempfile

    tmp = os.path.join(tempfile.gettempdir(), f"{avatar_id}.mp4")
    with open(tmp, "wb") as wf:
        wf.write(video_bytes)
    cap = cv2.VideoCapture(tmp)
    if not cap.isOpened():
        raise ValueError("无法解析驱动视频")
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
        if len(frames) >= 450:  # 上限 450 帧 ≈ 18 秒，支持 15 秒视频完整保留
            break
    cap.release()
    if len(frames) < 10:
        raise ValueError("驱动视频帧数过少（需 ≥10 帧）")
    try:
        os.remove(tmp)
    except Exception:
        pass

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    base = os.path.join(workdir, "data", "avatars", avatar_id)
    os.makedirs(os.path.join(base, "full_imgs"), exist_ok=True)
    os.makedirs(os.path.join(base, "face_imgs"), exist_ok=True)
    coords = []
    last_box = None
    for i, frame in enumerate(frames):
        img = _to_vertical(frame)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            last_box = (fx, fy, fw, fh)
        if last_box is None:
            fw = int(img.shape[1] * 0.6)
            fh = int(fw * 1.15)
            fx = (img.shape[1] - fw) // 2
            fy = int(img.shape[0] * 0.18)
        else:
            fx, fy, fw, fh = last_box
        x1, y1 = fx, fy
        x2, y2 = min(img.shape[1], fx + fw), min(img.shape[0], fy + fh + 10)
        face256 = cv2.resize(img[y1:y2, x1:x2], (256, 256))
        cv2.imwrite(f"{base}/full_imgs/{i:08d}.png", img)
        cv2.imwrite(f"{base}/face_imgs/{i:08d}.png", face256)
        coords.append((int(y1), int(y2), int(x1), int(x2)))
    with open(os.path.join(base, "coords.pkl"), "wb") as f:
        pickle.dump(coords, f)
    return base


async def _ensure_engine_online(engine_base: str, default_avatar: str = "wav2lip_avatar_female_model") -> bool:
    """确保引擎在线：探测失败则自动启动并等待就绪（最多约 90 秒）。"""
    try:
        engine_base = _validate_engine_base_url(engine_base)
    except ValueError:
        return False
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                await client.get(f"{engine_base}/api/avatar/tasks")
            return True
        except httpx.HTTPError:
            pass
        if attempt == 0:
            _restart_live_engine(default_avatar)
            for _ in range(30):
                await asyncio.sleep(3)
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                        await client.get(f"{engine_base}/api/avatar/tasks")
                    return True
                except httpx.HTTPError:
                    continue
    return False


async def _watch_engine_avatar_task(
    task_id: str, engine_base: str, engine_avatar_id: str
) -> None:
    """后台轮询引擎形象生成任务，完成后自动重启引擎用新形象；失败则清理。

    不依赖前端轮询（前端登出/关页也不影响），避免"生成了但没切换"。
    最长监控约 10 分钟；_restart_live_engine 幂等（已在用该形象则跳过）。
    """
    try:
        engine_base = _validate_engine_base_url(engine_base)
    except ValueError:
        return
    for _ in range(120):
        await asyncio.sleep(5)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                resp = await client.get(f"{engine_base}/api/avatar/task/{task_id}")
                data = resp.json().get("data") or {}
        except Exception:
            continue
        status = str(data.get("status") or "")
        if status == "completed":
            _restart_live_engine(engine_avatar_id)
            return
        if status == "failed":
            _restart_live_engine("wav2lip_avatar_female_model")
            return


async def _safe_watch_engine_avatar_task(
    task_id: str, engine_base: str, engine_avatar_id: str
) -> None:
    try:
        await _watch_engine_avatar_task(task_id, engine_base, engine_avatar_id)
    except Exception:
        return


def _prepare_engine_video(video_bytes: bytes) -> tuple[bytes, str]:
    """驱动视频达标检查 + 预处理（转 720x960 竖版 + 提亮），供引擎 s3fd 生成形象。

    先转竖版/提亮，再对预处理后的帧做检查（时长/亮度/haar 正脸检出率）——
    因为实际喂给引擎的就是预处理后的画面（竖版中心裁剪放大人脸、提亮）。
    不达标抛 ValueError（含明确指标与原因），避免引擎卡在 40% 人脸检测。
    """
    import cv2
    import numpy as np
    import tempfile

    def _to_vertical(frame):
        h, w = frame.shape[:2]
        if w / h > 3 / 4:
            tw = int(h * 3 / 4)
            x0 = (w - tw) // 2
            frame = frame[:, x0 : x0 + tw]
        else:
            th = int(w * 4 / 3)
            y0 = int((h - th) * 0.35)
            y0 = max(0, min(y0, h - th))
            frame = frame[y0 : y0 + th, :]
        return cv2.resize(frame, (720, 960))

    tmp = os.path.join(tempfile.gettempdir(), f"prep_{uuid.uuid4().hex}.mp4")
    with open(tmp, "wb") as f:
        f.write(video_bytes)
    cap = cv2.VideoCapture(tmp)
    if not cap.isOpened():
        raise ValueError("无法解析视频文件")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    if total < 150:
        raise ValueError(f"视频过短（{total} 帧 ≈ {total / fps:.0f} 秒），需 ≥6 秒（≥150 帧）")

    gamma = 1.2
    table = np.array([((i / 255.0) ** (1 / gamma)) * 255 for i in range(256)], dtype=np.uint8)
    processed: list = []
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        processed.append(cv2.LUT(_to_vertical(frame), table))
        if len(processed) >= 450:
            break
    cap.release()
    if not processed:
        raise ValueError("无法解析视频文件")

    step = max(1, len(processed) // 30)
    brightness = [float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()) for f in processed[::step]]
    sample = [
        len(cascade.detectMultiScale(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(80, 80))) > 0
        for f in processed[::step]
    ]
    avg_b = float(np.mean(brightness)) if brightness else 0
    rate = sum(sample) / len(sample) * 100 if sample else 0
    if avg_b < 45:
        raise ValueError(f"视频过暗（预处理后平均亮度 {avg_b:.0f}/255），请用光线充足的正面视频")
    if rate < 50:
        raise ValueError(
            f"未检测到清晰正脸（检出率 {rate:.0f}% <50%），请用正面、单人、面部清晰的视频"
        )

    out_tmp = os.path.join(tempfile.gettempdir(), f"prepout_{uuid.uuid4().hex}.mp4")
    vw = cv2.VideoWriter(out_tmp, cv2.VideoWriter_fourcc(*"mp4v"), 25, (720, 960))
    for frame in processed:
        vw.write(frame)
    vw.release()
    try:
        os.remove(tmp)
    except Exception:
        pass
    with open(out_tmp, "rb") as rf:
        video_data = rf.read()
    try:
        os.remove(out_tmp)
    except Exception:
        pass
    return video_data, "video/mp4"


def _stop_engine_processes() -> bool:
    """按监听端口停止本机 LiveTalking 引擎进程，跨平台。"""
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'listenport 8010' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
                ],
                timeout=30,
            )
            return True
        except Exception:
            return False
    for cmd in (["pkill", "-f", "listenport 8010"], ["fuser", "-k", "8010/tcp"]):
        try:
            subprocess.run(cmd, timeout=30, capture_output=True)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def _engine_process_uses_avatar(avatar_id: str) -> bool:
    if os.name == "nt":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'listenport 8010' } | "
                    "Select-Object -First 1 -ExpandProperty CommandLine",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            return avatar_id in out.stdout
        except Exception:
            return False
    try:
        out = subprocess.run(
            ["pgrep", "-af", "listenport 8010"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return avatar_id in out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _release_live_engine() -> bool:
    """停止本机 LiveTalking 引擎进程，释放 GPU。"""
    workdir = settings.LIVE_ENGINE_WORKDIR
    if not workdir or not os.path.isdir(workdir):
        return False
    return _stop_engine_processes()


def _restart_live_engine(avatar_id: str) -> bool:
    """重启本机 LiveTalking 引擎（--avatar_id <新形象>）。配置缺失或失败返回 False。"""
    workdir = settings.LIVE_ENGINE_WORKDIR
    venv = settings.LIVE_ENGINE_VENV
    if not workdir or not venv or not os.path.isfile(venv):
        return False
    # 幂等：当前引擎已在用该形象则跳过重启
    if _engine_process_uses_avatar(avatar_id):
        return True
    _stop_engine_processes()
    # 等端口 8010 释放，避免新进程因端口占用启动失败
    for _ in range(15):
        if not _port_in_use(8010):
            break
        time.sleep(1)
    log = open(os.path.join(workdir, "lt.log"), "a", encoding="utf-8")
    err = open(os.path.join(workdir, "lt.err.log"), "a", encoding="utf-8")
    try:
        cmd = [
            venv,
            "app.py",
            "--transport",
            "webrtc",
            "--model",
            "wav2lip",
            "--avatar_id",
            avatar_id,
            "--listenport",
            "8010",
        ]
        if os.name == "nt":
            subprocess.Popen(
                cmd,
                cwd=workdir,
                stdout=log,
                stderr=err,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            subprocess.Popen(
                cmd,
                cwd=workdir,
                stdout=log,
                stderr=err,
                start_new_session=True,
            )
        return True
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    """探测本机端口是否被占用。"""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return False
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        return True


@router.post("/live-avatars/{avatar_id}/sync-engine-static")
async def sync_avatar_to_engine_static(
    avatar_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把形象图同步为引擎静态 wav2lip 形象，并自动重启引擎使用它。

    流程：下载形象图 → 本地生成 full_imgs/face_imgs/coords.pkl → 写入引擎
    data/avatars/<airestro_xxx>/ → 更新形象 engine_avatar_id → 重启引擎
    （--avatar_id <airestro_xxx>）→ 引擎画面预览即显示该新形象。
    """
    avatar = await _get_avatar(avatar_id, current_user, db)
    video_url = (avatar.video_url or "").strip()
    image_url = (avatar.image_url or "").strip()
    if not video_url and not image_url:
        raise HTTPException(
            status_code=400, detail="该形象还没有驱动视频或形象图，请先上传 / AI 生成后保存"
        )
    if not settings.LIVE_ENGINE_WORKDIR or not os.path.isdir(settings.LIVE_ENGINE_WORKDIR):
        raise HTTPException(
            status_code=400, detail="未配置引擎目录（LIVE_ENGINE_WORKDIR），无法同步到引擎"
        )
    engine_aid = f"airestro_{uuid.uuid4().hex[:12]}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            source_url = video_url or image_url
            try:
                source_url = await asyncio.to_thread(_validate_media_url_host, source_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            avatar_root = os.path.join(settings.LIVE_ENGINE_WORKDIR, "data", "avatars")
            if os.path.isdir(avatar_root):
                avatar_count = sum(
                    1 for name in os.listdir(avatar_root) if name.startswith("airestro_")
                )
                if avatar_count >= _MAX_ENGINE_AVATAR_DIRS:
                    raise HTTPException(
                        status_code=429, detail="引擎形象数量过多，请清理后重试"
                    )
            r = await client.get(source_url)
            r.raise_for_status()
            source_bytes = r.content
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"下载形象素材失败：{_engine_exc_text(exc)}")
    try:
        if video_url:
            avatar_dir = _build_dynamic_avatar(source_bytes, settings.LIVE_ENGINE_WORKDIR, engine_aid)
            kind = "dynamic"
        else:
            avatar_dir = _build_static_avatar(source_bytes, settings.LIVE_ENGINE_WORKDIR, engine_aid)
            kind = "static"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"生成引擎形象失败：{exc}")
    avatar.engine_avatar_id = engine_aid
    await db.flush()
    restarted = _restart_live_engine(engine_aid)
    return {
        "engine_avatar_id": engine_aid,
        "restarted": restarted,
        "dir": avatar_dir,
        "kind": kind,
    }


@router.post("/live-engines/release")
async def release_live_engine(
    current_user: User = Depends(_require_admin),
):
    """停止本地引擎，释放 GPU（结束直播/长时间不播时使用）。"""
    released = _release_live_engine()
    return {"released": released}


@router.post("/live-engines/start")
async def start_live_engine(
    body: EngineAvatarCreateRequest | None = None,
    current_user: User = Depends(_require_admin),
):
    """启动本地引擎（--avatar_id 默认用引擎当前形象；可传 engine_base_url 覆盖地址）。"""
    avatar_id = ""
    if body and body.engine_base_url:
        # 兼容传地址参数；实际启动用默认形象
        pass
    restarted = _restart_live_engine(avatar_id or "wav2lip_avatar_female_model")
    return {"started": restarted}


@router.post("/live-avatars", response_model=LiveAvatarOut)
async def create_avatar(
    body: LiveAvatarCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    avatar = LiveAvatar(org_id=current_user.id, **body.model_dump())
    db.add(avatar)
    await db.flush()
    return avatar


@router.get("/live-avatars", response_model=LiveAvatarListResponse)
async def list_avatars(
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(LiveAvatar).where(LiveAvatar.org_id == current_user.id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(LiveAvatar.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return LiveAvatarListResponse(items=list(rows), total=total, page=page, size=page_size)


@router.get("/live-avatars/{avatar_id}", response_model=LiveAvatarOut)
async def get_avatar(
    avatar_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_avatar(avatar_id, current_user, db)


@router.patch("/live-avatars/{avatar_id}", response_model=LiveAvatarOut)
async def update_avatar(
    avatar_id: str,
    body: LiveAvatarUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    avatar = await _get_avatar(avatar_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(avatar, field, value)
    return avatar


@router.delete("/live-avatars/{avatar_id}")
async def delete_avatar(
    avatar_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    avatar = await _get_avatar(avatar_id, current_user, db)
    ref_script = (
        await db.execute(
            select(LiveScript.id).where(LiveScript.avatar_id == avatar.id).limit(1)
        )
    ).scalar_one_or_none()
    if ref_script:
        raise HTTPException(status_code=409, detail="该形象已被直播脚本引用，无法删除")
    ref_session = (
        await db.execute(
            select(LiveSession.id).where(LiveSession.avatar_id == avatar.id).limit(1)
        )
    ).scalar_one_or_none()
    if ref_session:
        raise HTTPException(status_code=409, detail="该形象已被场次引用，无法删除")
    await db.delete(avatar)
    await db.flush()
    return {"ok": True}


# ============================================================
# 直播脚本
# ============================================================


@router.post(
    "/live-projects/{project_id}/scripts/generate", response_model=LiveScriptOut
)
async def generate_script(
    project_id: str,
    body: ScriptGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    rate_key = f"live:scripts:generate:{current_user.id}:{project.shop_id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(
            status_code=429, detail=f"操作过于频繁，请 {_RATE_TTL_SCRIPTS} 秒后再试"
        )

    # 解析形象：显式传 avatar_id 校验 org 归属；缺省取最近一次生成用过的形象
    avatar: LiveAvatar | None = None
    if body.avatar_id is not None:
        avatar = await _get_avatar_by_uuid(body.avatar_id, current_user, db)
    else:
        latest = await _latest_script(project.id, db)
        if latest is None or latest.avatar_id is None:
            raise HTTPException(
                status_code=400,
                detail="项目尚未生成过脚本，请显式指定数字人形象 avatar_id",
            )
        avatar = await _get_avatar_by_uuid(latest.avatar_id, current_user, db)
        if avatar.status == "disabled":
            raise HTTPException(
                status_code=400,
                detail="默认形象已停用，请显式指定其他形象 avatar_id",
            )

    # AI 标识文案缺省自动填充
    if not (project.ai_label_text and project.ai_label_text.strip()):
        project.ai_label_text = _DEFAULT_AI_LABEL

    shop = await db.get(Shop, project.shop_id)
    agent = LiveScriptAgent()
    try:
        data = await agent.generate(
            shop_name=shop.name if shop else "",
            category=shop.category if shop else None,
            platform=project.platform,
            goal=project.goal,
            promo_items=project.promo_items,
            persona=avatar.persona if avatar else None,
            tone=body.tone,
            duration_min=body.duration_min,
        )
    except LiveScriptAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    current_max = (
        await db.execute(
            select(func.max(LiveScript.generation_batch)).where(
                LiveScript.project_id == project.id
            )
        )
    ).scalar_one()
    batch = (current_max or 0) + 1
    # regenerate 语义：旧批次全部归档（含 edited/confirmed），内容不代入
    await db.execute(
        update(LiveScript)
        .where(LiveScript.project_id == project.id)
        .values(is_archived=True)
    )

    script = LiveScript(
        project_id=project.id,
        avatar_id=avatar.id if avatar else None,
        persona_snapshot=dict(avatar.persona) if avatar and avatar.persona else None,
        generation_batch=batch,
        title=data["title"],
        tone=data["tone"],
        content=data["content"],
        total_duration_sec=data["total_duration_sec"],
        status="draft",
        is_archived=False,
    )
    db.add(script)
    await db.flush()
    project.status = "active"

    # 仅生成成功才计入频控
    await set_rate_limit(rate_key, _RATE_TTL_SCRIPTS)
    return script


@router.get("/live-projects/{project_id}/scripts", response_model=list[LiveScriptOut])
async def list_scripts(
    project_id: str,
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    stmt = select(LiveScript).where(LiveScript.project_id == project.id)
    if not include_archived:
        stmt = stmt.where(LiveScript.is_archived.is_(False))
    rows = (
        await db.execute(stmt.order_by(LiveScript.generation_batch.desc()))
    ).scalars().all()
    return list(rows)


@router.get("/live-projects/{project_id}/scripts/{sid}", response_model=LiveScriptOut)
async def get_script(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    return await _get_script(project, sid, db)


@router.put("/live-projects/{project_id}/scripts/{sid}", response_model=LiveScriptOut)
async def update_script(
    project_id: str,
    sid: str,
    body: ScriptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """人工编辑脚本，status=edited；confirmed 禁止 PUT。"""
    project = await _get_project(project_id, current_user, db)
    script = await _get_script(project, sid, db)
    if script.status == "confirmed":
        raise HTTPException(status_code=400, detail="已定稿脚本禁止修改")
    data = body.model_dump(exclude_unset=True)
    if "content" in data and data["content"] is not None:
        data["total_duration_sec"] = sum(s["duration_sec"] for s in data["content"])
    for field, value in data.items():
        setattr(script, field, value)
    script.status = "edited"
    return script


@router.post(
    "/live-projects/{project_id}/scripts/{sid}/confirm", response_model=LiveScriptOut
)
async def confirm_script(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """合规自检通过后定稿；pass=false → 422；幂等。"""
    project = await _get_project(project_id, current_user, db)
    script = await _get_script(project, sid, db)
    if script.status == "confirmed":
        return script
    result = LiveCompliance.check(
        ai_label_text=project.ai_label_text,
        persona_snapshot=script.persona_snapshot,
        content=script.content,
    )
    if not result["pass"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "合规自检未通过", "items": result["items"]},
        )
    script.status = "confirmed"
    script.compliance = result
    return script


@router.delete("/live-projects/{project_id}/scripts/{sid}")
async def delete_script(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    script = await _get_script(project, sid, db)
    if script.status == "confirmed":
        raise HTTPException(status_code=400, detail="已定稿脚本禁止删除")
    try:
        await db.delete(script)
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="脚本已被场次引用，无法删除")
    return {"ok": True}


@router.post(
    "/live-projects/{project_id}/scripts/{sid}/export",
    response_model=LiveExportBundle,
)
async def export_script(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出开播包：仅当前活跃批次（未归档）的 confirmed 脚本可导出。"""
    project = await _get_project(project_id, current_user, db)
    script = await _get_script(project, sid, db)
    if script.is_archived:
        raise HTTPException(
            status_code=400,
            detail="该脚本已归档，如需留档请通过 GET 查看，不支持导出开播包",
        )
    if script.status != "confirmed":
        raise HTTPException(status_code=400, detail="脚本未定稿，无法导出开播包")

    compliance = dict(script.compliance) if script.compliance else None
    if compliance is None:
        compliance = LiveCompliance.check(
            ai_label_text=project.ai_label_text,
            persona_snapshot=script.persona_snapshot,
            content=script.content,
        )
    items = list(compliance.get("items", []))

    danmaku = (
        await db.execute(
            select(LiveDanmakuConfig).where(
                LiveDanmakuConfig.project_id == project.id
            )
        )
    ).scalar_one_or_none()

    # persona_json 优先级：弹幕配置 persona → 脚本人设快照 → 默认占位 + 提示
    persona_json: dict[str, Any]
    if danmaku and danmaku.persona:
        persona_json = dict(danmaku.persona)
    elif script.persona_snapshot:
        persona_json = dict(script.persona_snapshot)
    else:
        persona_json = dict(_DEFAULT_PERSONA)
        items.append(
            {
                "key": "persona_placeholder",
                "ok": True,
                "detail": "未配置人设，导出包使用默认占位人设，请按实际形象调整",
            }
        )

    persona_json = _normalize_persona_for_engine(persona_json)

    # 弹幕规则
    if danmaku is None:
        reply_rules: list[dict] = []
        wordlist: list[str] = default_wordlist()
        items.append(
            {
                "key": "danmaku_missing",
                "ok": True,
                "detail": "未配置弹幕互动规则（导出包 reply_rules 为空，请使用候选话术人工粘贴）",
            }
        )
    else:
        reply_rules = list(danmaku.reply_rules or [])
        wordlist = list(danmaku.sensitive_words or [])
        if danmaku.source_script_id != script.id:
            items.append(
                {
                    "key": "danmaku_stale",
                    "ok": True,
                    "detail": "弹幕规则基于其他脚本版本生成，建议重新生成",
                }
            )

    # 形象声音配置 → 追加到 engine_guide，随开播包直达值守人（TTS 提供方/音色）
    tts_line = ""
    if script.avatar_id:
        avatar = await _get_avatar_by_uuid(script.avatar_id, current_user, db)
        vc = avatar.voice_config or {}
        provider = str(vc.get("provider") or "edgetts").strip() or "edgetts"
        voice = str(vc.get("voice") or "").strip()
        flags = [f"--tts {provider}"]
        if voice:
            flags.append(f"--REF_FILE {voice}")
        tts_line = (
            f"\n8. 引擎 TTS 配置（形象 {avatar.name}）："
            + " ".join(flags)
            + "；语速/音调如需调节按引擎 TTS 文档设置"
        )

    compliance = {"pass": compliance.get("pass", True), "items": items}
    return LiveExportBundle(
        script_markdown=_build_script_markdown(script),
        persona_json=persona_json,
        wordlist=wordlist,
        reply_rules=reply_rules,
        compliance=compliance,
        engine_guide=_build_engine_guide(
            project, project.ai_label_text or _DEFAULT_AI_LABEL
        )
        + tts_line,
    )


# ============================================================
# 弹幕互动配置
# ============================================================


@router.post(
    "/live-projects/{project_id}/danmaku-config/generate",
    response_model=LiveDanmakuConfigOut,
)
async def generate_danmaku_config(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """覆盖式生成弹幕规则；前置：项目存在当前活跃批次的 confirmed 脚本；失败保留旧配置。"""
    project = await _get_project(project_id, current_user, db)
    rate_key = f"live:danmaku:generate:{current_user.id}:{project.shop_id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(
            status_code=429, detail=f"操作过于频繁，请 {_RATE_TTL_DANMAKU} 秒后再试"
        )

    script = await _active_confirmed_script(project.id, db)
    if script is None:
        raise HTTPException(
            status_code=400,
            detail="项目必须存在当前活跃批次的已定稿脚本，才能生成弹幕规则",
        )

    existing = (
        await db.execute(
            select(LiveDanmakuConfig).where(
                LiveDanmakuConfig.project_id == project.id
            )
        )
    ).scalar_one_or_none()
    persona_input = None
    if existing and existing.persona:
        persona_input = existing.persona
    else:
        persona_input = script.persona_snapshot

    agent = LiveDanmakuAgent()
    try:
        data = await agent.generate(
            platform=project.platform,
            persona=persona_input,
            script={"title": script.title, "content": script.content},
        )
    except LiveDanmakuAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    # 仅在 AI 成功返回且通过校验后一次性落库；失败时旧配置原样保留
    if existing:
        existing.persona = data["persona"]
        existing.reply_rules = data["reply_rules"]
        existing.sensitive_words = data["sensitive_words"]
        existing.escalate_topics = data["escalate_topics"]
        existing.source_script_id = script.id
        config = existing
    else:
        config = LiveDanmakuConfig(
            project_id=project.id,
            source_script_id=script.id,
            persona=data["persona"],
            reply_rules=data["reply_rules"],
            sensitive_words=data["sensitive_words"],
            escalate_topics=data["escalate_topics"],
        )
        db.add(config)
    await db.flush()

    await set_rate_limit(rate_key, _RATE_TTL_DANMAKU)
    return config


@router.get(
    "/live-projects/{project_id}/danmaku-config", response_model=LiveDanmakuConfigOut
)
async def get_danmaku_config(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    config = (
        await db.execute(
            select(LiveDanmakuConfig).where(
                LiveDanmakuConfig.project_id == project.id
            )
        )
    ).scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="尚未生成弹幕互动规则")
    return config


@router.put(
    "/live-projects/{project_id}/danmaku-config", response_model=LiveDanmakuConfigOut
)
async def update_danmaku_config(
    project_id: str,
    body: DanmakuConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """人工编辑弹幕配置；未生成过则创建（source_script_id 为空）。"""
    project = await _get_project(project_id, current_user, db)
    config = (
        await db.execute(
            select(LiveDanmakuConfig).where(
                LiveDanmakuConfig.project_id == project.id
            )
        )
    ).scalar_one_or_none()
    data = body.model_dump(exclude_unset=True)
    if config is None:
        config = LiveDanmakuConfig(project_id=project.id, **data)
        db.add(config)
    else:
        for field, value in data.items():
            setattr(config, field, value)
    await db.flush()
    return config


# ============================================================
# 合规自检
# ============================================================


@router.post(
    "/live-projects/{project_id}/compliance/check", response_model=ComplianceResult
)
async def compliance_check(
    project_id: str,
    body: ComplianceCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回 { pass, items }，不落库；confirm 时才快照。"""
    project = await _get_project(project_id, current_user, db)
    script: LiveScript | None
    if body.script_id is not None:
        script = await _get_script(project, str(body.script_id), db)
    else:
        script = await _active_confirmed_script(project.id, db)
        if script is None:
            script = await _latest_script(project.id, db)
    if script is None:
        raise HTTPException(
            status_code=400, detail="项目尚无直播脚本，无法进行合规自检"
        )
    result = LiveCompliance.check(
        ai_label_text=project.ai_label_text,
        persona_snapshot=script.persona_snapshot,
        content=script.content,
    )
    return ComplianceResult(pass_=result["pass"], items=result["items"])


# ============================================================
# 场次与复盘
# ============================================================


@router.post("/live-projects/{project_id}/sessions", response_model=LiveSessionOut)
async def create_session(
    project_id: str,
    body: LiveSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    if body.avatar_id is not None:
        await _get_avatar_by_uuid(body.avatar_id, current_user, db)
    if body.script_id is not None:
        await _get_script(project, str(body.script_id), db)
    if body.operator_id is not None:
        await _validate_operator(body.operator_id, db)
    session = LiveSession(
        project_id=project.id,
        script_id=body.script_id,
        avatar_id=body.avatar_id,
        scheduled_at=body.scheduled_at,
        duration_min=body.duration_min,
        operator_id=body.operator_id,
        notes=body.notes,
        status="planned",
        duty_confirmed=False,
        ai_label_confirmed=False,
        is_backfilled=False,
    )
    db.add(session)
    await db.flush()
    return session


@router.get(
    "/live-projects/{project_id}/sessions", response_model=LiveSessionListResponse
)
async def list_sessions(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    base = select(LiveSession).where(LiveSession.project_id == project.id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(LiveSession.scheduled_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return LiveSessionListResponse(items=list(rows), total=total, page=page, size=page_size)


@router.get("/live-projects/{project_id}/sessions/{sid}", response_model=LiveSessionOut)
async def get_session(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    return await _get_session(project, sid, db)


@router.patch("/live-projects/{project_id}/sessions/{sid}", response_model=LiveSessionOut)
async def update_session(
    project_id: str,
    sid: str,
    body: LiveSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑排期 + 状态流转；可编辑字段受状态限制，终态仅 notes。"""
    project = await _get_project(project_id, current_user, db)
    session = await _get_session(project, sid, db)
    data = body.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    started_at = data.pop("started_at", None)
    ended_at = data.pop("ended_at", None)

    if session.status in ("ended", "cancelled"):
        if (
            (set(data) - {"notes"})
            or new_status is not None
            or started_at is not None
            or ended_at is not None
        ):
            raise HTTPException(
                status_code=400, detail="已结束/已取消场次为终态，仅允许修改 notes"
            )
        if "notes" in data:
            session.notes = data["notes"]
        return session

    if session.status == "live":
        if (
            (set(data) - {"notes"})
            or started_at is not None
            or ended_at is not None
        ):
            raise HTTPException(
                status_code=400,
                detail="已开播场次排期与绑定字段已锁定，仅允许修改 notes 或结束场次",
            )
        if new_status is not None:
            if new_status != "ended":
                raise HTTPException(
                    status_code=400, detail="已开播场次仅可流转到 ended"
                )
            session.status = "ended"
            # 结束直播 → 自动释放引擎 GPU
            _release_live_engine()
        if "notes" in data:
            session.notes = data["notes"]
        return session

    # planned
    editable = {
        "script_id",
        "avatar_id",
        "scheduled_at",
        "duration_min",
        "operator_id",
        "notes",
        "duty_confirmed",
        "ai_label_confirmed",
    }
    invalid = set(data) - editable
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"planned 状态不允许修改字段: {','.join(sorted(invalid))}",
        )

    if data.get("avatar_id") is not None:
        await _get_avatar_by_uuid(data["avatar_id"], current_user, db)
    if data.get("script_id") is not None:
        await _get_script(project, str(data["script_id"]), db)
    if data.get("operator_id") is not None:
        await _validate_operator(data["operator_id"], db)
    if data.get("duty_confirmed") is True and (
        data.get("operator_id") or session.operator_id
    ) is None:
        raise HTTPException(
            status_code=422, detail="值守确认（duty_confirmed）必须同时填写值守人 operator_id"
        )

    for field, value in data.items():
        setattr(session, field, value)

    if new_status == "live":
        unmet: list[str] = []
        if not (session.duty_confirmed and session.operator_id is not None):
            unmet.append("duty_confirmed 为 true 且 operator_id 非空")
        if not session.ai_label_confirmed:
            unmet.append("ai_label_confirmed 为 true")
        if session.script_id is not None:
            script = await db.get(LiveScript, session.script_id)
            if script is None or script.status != "confirmed" or script.is_archived:
                unmet.append("关联脚本必须是当前活跃批次的已定稿脚本（confirmed 且未归档）")
        if unmet:
            raise HTTPException(
                status_code=422,
                detail={"message": "开播前置条件未满足", "items": unmet},
            )
        session.status = "live"
    elif new_status == "cancelled":
        session.status = "cancelled"
    elif new_status == "ended":
        if started_at is None or ended_at is None:
            raise HTTPException(
                status_code=422,
                detail="补录场次必须同时提供 started_at 与 ended_at",
            )
        session.started_at = started_at
        session.ended_at = ended_at
        session.is_backfilled = True
        session.status = "ended"
    elif new_status not in (None, "planned"):
        raise HTTPException(status_code=400, detail=f"非法状态流转: {new_status}")
    return session


@router.delete("/live-projects/{project_id}/sessions/{sid}")
async def delete_session(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    session = await _get_session(project, sid, db)
    if session.status != "planned":
        raise HTTPException(status_code=400, detail="仅可删除 planned 状态的场次")
    await db.delete(session)
    await db.flush()
    return {"ok": True}


@router.post(
    "/live-projects/{project_id}/sessions/{sid}/metrics",
    response_model=LiveSessionMetricOut,
)
async def upsert_metrics(
    project_id: str,
    sid: str,
    body: MetricsCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动录入复盘数据（每场一条，重复提交覆盖）。"""
    project = await _get_project(project_id, current_user, db)
    session = await _get_session(project, sid, db)
    metric = (
        await db.execute(
            select(LiveSessionMetric).where(
                LiveSessionMetric.session_id == session.id
            )
        )
    ).scalar_one_or_none()
    if metric:
        metric.metrics = body.metrics
        metric.source = body.source
    else:
        metric = LiveSessionMetric(
            session_id=session.id, metrics=body.metrics, source=body.source
        )
        db.add(metric)
        await db.flush()
    return metric


@router.get(
    "/live-projects/{project_id}/sessions/{sid}/metrics",
    response_model=LiveSessionMetricOut,
)
async def get_metrics(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    session = await _get_session(project, sid, db)
    metric = (
        await db.execute(
            select(LiveSessionMetric).where(
                LiveSessionMetric.session_id == session.id
            )
        )
    ).scalar_one_or_none()
    if metric is None:
        raise HTTPException(status_code=404, detail="该场次暂无复盘数据")
    return metric


@router.post(
    "/live-projects/{project_id}/sessions/{sid}/review", response_model=ReviewResponse
)
async def review_session(
    project_id: str,
    sid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 复盘写入 metrics.ai_review；频控 30s（user+session_id，成功才计入）。"""
    project = await _get_project(project_id, current_user, db)
    session = await _get_session(project, sid, db)
    rate_key = f"live:review:{current_user.id}:{session.id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(
            status_code=429, detail=f"操作过于频繁，请 {_RATE_TTL_REVIEW} 秒后再试"
        )

    metric = (
        await db.execute(
            select(LiveSessionMetric).where(
                LiveSessionMetric.session_id == session.id
            )
        )
    ).scalar_one_or_none()
    if metric is None or not metric.metrics:
        raise HTTPException(status_code=400, detail="该场次暂无复盘数据，请先录入 metrics")

    script_summary: str | None = None
    if session.script_id:
        script = await db.get(LiveScript, session.script_id)
        if script:
            script_summary = f"{script.title}（总时长 {script.total_duration_sec}s）"

    agent = LiveReviewAgent()
    try:
        review = await agent.review(metrics=metric.metrics, script_summary=script_summary)
    except LiveReviewAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    metric.ai_review = review
    await set_rate_limit(rate_key, _RATE_TTL_REVIEW)
    return ReviewResponse(ai_review=review)

