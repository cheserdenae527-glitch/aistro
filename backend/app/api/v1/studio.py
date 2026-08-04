"""内容工坊模块 API — 项目 CRUD + 文案生成 + 卡组渲染/QA + 导出到视觉设计。

鉴权：所有端点校验 JWT + shop 所有权（project -> shop -> merchant -> user）。
"""
from __future__ import annotations

import asyncio
import io
import json
import uuid

import openai

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.studio_copy import StudioAgentError, StudioCopyAgent
from app.ai.studio_image_prompt import ImagePromptAgentError, StudioImagePromptAgent
from app.ai.studio_paginate import StudioPaginateAgent, StudioPaginateError
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.models.design_asset import DesignAsset
from app.models.design_project import DesignProject
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.studio_copy import StudioCopy
from app.models.studio_deck import StudioDeck
from app.models.studio_project import StudioProject
from app.models.user import User
from app.schemas.studio import (
    CopyGenerateRequest,
    CopyGenerateResponse,
    CopyUpdateRequest,
    ImagePromptEnrichRequest,
    ImagePromptEnrichResponse,
    DeckCreateRequest,
    DeckCreateResponse,
    ExportToDesignResponse,
    StudioCopySummary,
    StudioDeckSummary,
    StudioProjectCreate,
    StudioProjectDetail,
    StudioProjectResponse,
    StudioProjectUpdate,
)
from app.services.storage import (
    get_object_bytes,
    get_presigned_url,
    safe_get_presigned_url,
    upload_bytes,
)
from app.services.studio_qa import build_qa_report
from app.services.studio_render import build_page_html, render_pages
from app.services.studio_themes import theme_paper

router = APIRouter(tags=["studio"])

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_MAX_UPLOAD_FILES = 8
_XHS_W, _XHS_H = 1080, 1440


# ============================================================
# 鉴权与资源 helper
# ============================================================


async def _verify_shop_owner(shop_id: str, user: User, db: AsyncSession) -> Shop:
    result = await db.execute(
        select(Shop)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Shop.id == shop_id, Merchant.user_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def _get_project(project_id: str, user: User, db: AsyncSession) -> StudioProject:
    result = await db.execute(
        select(StudioProject)
        .join(Shop, StudioProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(StudioProject.id == project_id, Merchant.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_copy(copy_id: str, user: User, db: AsyncSession) -> StudioCopy:
    result = await db.execute(
        select(StudioCopy)
        .join(StudioProject, StudioCopy.project_id == StudioProject.id)
        .join(Shop, StudioProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(StudioCopy.id == copy_id, Merchant.user_id == user.id)
    )
    copy = result.scalar_one_or_none()
    if not copy:
        raise HTTPException(status_code=404, detail="Copy not found")
    return copy


async def _get_deck(deck_id: str, user: User, db: AsyncSession) -> StudioDeck:
    result = await db.execute(
        select(StudioDeck)
        .join(StudioProject, StudioDeck.project_id == StudioProject.id)
        .join(Shop, StudioProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(StudioDeck.id == deck_id, Merchant.user_id == user.id)
    )
    deck = result.scalar_one_or_none()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


def _rate_key(action: str, user: User, shop_id: uuid.UUID) -> str:
    return f"studio:{action}:{user.id}:{shop_id}"


def _presign_assets(source_assets: list | None) -> list[dict]:
    out: list[dict] = []
    for item in source_assets or []:
        row = dict(item)
        if row.get("url"):
            row["url"] = safe_get_presigned_url(row["url"]) or row["url"]
        out.append(row)
    return out


def _deck_response(deck: StudioDeck) -> dict:
    resp = StudioDeckSummary.model_validate(deck).model_dump()
    if resp.get("images"):
        resp["images"] = [
            {
                **img,
                "url": safe_get_presigned_url(img["url"]) or img["url"],
            }
            for img in resp["images"]
        ]
    if resp.get("source_assets"):
        resp["source_assets"] = _presign_assets(resp["source_assets"])
    return resp


def _make_thumb(data: bytes) -> bytes:
    """生成最长边 320px 的 JPEG 缩略图。"""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((320, 320), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


async def _load_design_asset_urls(
    asset_ids: list[uuid.UUID], project: StudioProject, user: User, db: AsyncSession
) -> tuple[list[dict], list[str]]:
    """校验素材所有权（当前 shop 的 design_projects，active 或 AI 生成的 pending 候选），返回 source_assets + 渲染 URL。"""
    source_assets: list[dict] = []
    urls: list[str] = []
    for asset_id in asset_ids:
        result = await db.execute(
            select(DesignAsset)
            .join(DesignProject, DesignAsset.project_id == DesignProject.id)
            .where(
                DesignAsset.id == asset_id,
                DesignAsset.status.in_(["active", "pending"]),
                DesignProject.shop_id == project.shop_id,
            )
        )
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(
                status_code=404, detail=f"素材不存在或不属于当前门店: {asset_id}"
            )
        object_name = asset.processed_url or asset.original_url
        if not object_name:
            raise HTTPException(status_code=400, detail="素材缺少图片文件")
        source_assets.append(
            {"source": "design", "asset_id": str(asset.id), "url": object_name}
        )
        urls.append(get_presigned_url(object_name))
    return source_assets, urls


# ============================================================
# 项目 CRUD
# ============================================================


@router.post(
    "/studio/projects",
    response_model=StudioProjectResponse,
)
async def create_project(
    body: StudioProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(str(body.shop_id), current_user, db)
    project = StudioProject(shop_id=body.shop_id, title=body.title)
    db.add(project)
    await db.flush()
    return project


@router.get(
    "/studio/projects",
    response_model=list[StudioProjectResponse],
)
async def list_projects(
    shop_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(StudioProject)
        .join(Shop, StudioProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Merchant.user_id == current_user.id)
        .order_by(StudioProject.updated_at.desc())
    )
    if shop_id is not None:
        query = query.where(StudioProject.shop_id == shop_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/studio/projects/{project_id}",
    response_model=StudioProjectDetail,
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    copies = (
        await db.execute(
            select(StudioCopy)
            .where(StudioCopy.project_id == project.id)
            .order_by(StudioCopy.created_at.desc())
        )
    ).scalars().all()
    decks = (
        await db.execute(
            select(StudioDeck)
            .where(StudioDeck.project_id == project.id)
            .order_by(StudioDeck.created_at.desc())
        )
    ).scalars().all()
    detail = StudioProjectDetail.model_validate(project).model_dump()
    detail["copies"] = [StudioCopySummary.model_validate(c).model_dump() for c in copies]
    detail["decks"] = [_deck_response(d) for d in decks]
    return detail


@router.patch(
    "/studio/projects/{project_id}",
    response_model=StudioProjectResponse,
)
async def update_project(
    project_id: str,
    body: StudioProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    await db.flush()
    return project


@router.delete("/studio/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    await db.delete(project)
    await db.flush()
    return {"ok": True}


# ============================================================
# 文案生成
# ============================================================


@router.post(
    "/studio/projects/{project_id}/copy/generate",
    response_model=CopyGenerateResponse,
)
async def generate_copy(
    project_id: str,
    body: CopyGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    if not await check_rate_limit(
        _rate_key("copy", current_user, project.shop_id), ttl_seconds=20
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后再试")

    try:
        data = await StudioCopyAgent().generate(
            category=body.category,
            style=body.style,
            price_range=body.price_range,
            topic=body.topic,
            shop_name=body.shop_name,
        )
    except StudioAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 文案服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 文案服务暂时不可用: {exc}")

    copy = StudioCopy(
        project_id=project.id,
        input_payload=body.model_dump(),
        titles=data["titles"],
        body=data["body"],
        tags=data["tags"],
        image_guide=data["image_guide"],
    )
    db.add(copy)
    project.status = "generated"
    await db.flush()
    return copy


@router.patch(
    "/studio/copies/{copy_id}",
    response_model=StudioCopySummary,
)
async def update_copy(
    copy_id: str,
    body: CopyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    copy = await _get_copy(copy_id, current_user, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(copy, key, value)
    await db.flush()
    return copy


# ============================================================
# 卡组生成
# ============================================================


@router.post(
    "/studio/copies/{copy_id}/image-prompt/enrich",
    response_model=ImagePromptEnrichResponse,
)
async def enrich_image_prompt(
    copy_id: str,
    body: ImagePromptEnrichRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    copy = await _get_copy(copy_id, current_user, db)
    if not await check_rate_limit(
        _rate_key("image-prompt", current_user, copy.project_id), ttl_seconds=20
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后再试")

    try:
        result = await StudioImagePromptAgent().enrich(
            body.direction, copy.input_payload or {}
        )
    except ImagePromptAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    return ImagePromptEnrichResponse(**result)


@router.post(
    "/studio/projects/{project_id}/decks",
    response_model=DeckCreateResponse,
)
async def create_deck(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    if not await check_rate_limit(
        _rate_key("deck", current_user, project.shop_id), ttl_seconds=60
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后再试")

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        params, files = await _parse_deck_form(request)
    else:
        params, files = await _parse_deck_json(request)

    copy_id = params["copy_id"]
    template = params["template"]
    theme = params["theme"]
    page_count = params["page_count"]
    if not (4 <= page_count <= 8):
        raise HTTPException(status_code=400, detail="page_count 必须在 4-8 之间")

    copy = await _get_copy(str(copy_id), current_user, db)
    if copy.project_id != project.id:
        raise HTTPException(status_code=400, detail="文案不属于该项目")

    try:
        theme_paper(template, theme)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知模板或色板: {template}/{theme}")

    # 素材来源：直接上传 + 素材库引用可同时使用
    source_assets, urls = await _collect_source_assets(
        files, params["asset_ids"], project, current_user, db
    )

    # 分页 LLM
    try:
        page_specs = await StudioPaginateAgent().paginate(
            copy.body or "", page_count, len(urls)
        )
    except StudioPaginateError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 分页服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 分页服务暂时不可用: {exc}")

    # 渲染 + QA + 上传
    htmls: list[str] = []
    for i, spec in enumerate(page_specs):
        image_index = spec.get("image_index")
        image_url = None
        if image_index is not None and 0 <= int(image_index) < len(urls):
            image_url = urls[int(image_index)]
        htmls.append(
            build_page_html(
                template=template,
                theme=theme,
                title=spec["title"],
                bullets=spec["bullets"],
                image_url=image_url,
                shop_name=copy.input_payload.get("shop_name", "") if copy.input_payload else "",
                category=copy.input_payload.get("category", "") if copy.input_payload else "",
                topic=copy.input_payload.get("topic", "") if copy.input_payload else "",
                page_num=i + 1,
                page_total=page_count,
                is_cover=(i == 0),
            )
        )

    deck = StudioDeck(
        project_id=project.id,
        copy_id=copy.id,
        template=template,
        theme=theme,
        page_count=page_count,
        page_specs=page_specs,
        source_assets=source_assets,
        status="failed",
        error_message=None,
    )
    db.add(deck)

    try:
        rendered = await asyncio.to_thread(render_pages, htmls)
    except Exception as exc:  # noqa: BLE001 — 渲染失败记录到卡组
        deck.error_message = f"渲染失败: {exc}"
        await db.flush()
        return DeckCreateResponse(
            deck_id=deck.id,
            images=[],
            qa_report=None,
            status="failed",
            error_message=deck.error_message,
        )

    paper = theme_paper(template, theme)
    images: list[dict] = []
    qa_pages: list[dict] = []
    all_pass = True
    for i, item in enumerate(rendered):
        qa = build_qa_report(item["png"], item["metrics"], paper)
        qa_pages.append({"page": i + 1, **qa})
        if not qa["pass"]:
            all_pass = False
        object_name = upload_bytes(item["png"], "image/png", folder="studio")
        images.append(
            {
                "page": i + 1,
                "url": object_name,
                "width": _XHS_W,
                "height": _XHS_H,
            }
        )

    deck.images = images
    deck.qa_report = {"all_pass": all_pass, "pages": qa_pages}
    deck.status = "rendered"
    await db.flush()

    return DeckCreateResponse(
        deck_id=deck.id,
        images=[
            {
                **img,
                "url": safe_get_presigned_url(img["url"]) or img["url"],
            }
            for img in images
        ],
        qa_report=deck.qa_report,
        status=deck.status,
        error_message=deck.error_message,
    )


async def _parse_deck_json(request: Request) -> tuple[dict, list[UploadFile]]:
    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")
    try:
        body = DeckCreateRequest.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"参数校验失败: {exc}")
    return {
        "copy_id": body.copy_id,
        "template": body.template,
        "theme": body.theme,
        "page_count": body.page_count,
        "asset_ids": body.asset_ids,
    }, []


async def _parse_deck_form(request: Request) -> tuple[dict, list[UploadFile]]:
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="multipart 表单解析失败")
    try:
        copy_id = uuid.UUID(str(form.get("copy_id", "")))
    except Exception:
        raise HTTPException(status_code=400, detail="copy_id 无效")
    template = str(form.get("template", ""))
    theme = str(form.get("theme", ""))
    if template not in ("editorial", "swiss"):
        raise HTTPException(status_code=400, detail="template 必须是 editorial 或 swiss")
    try:
        page_count = int(str(form.get("page_count", "")))
    except Exception:
        raise HTTPException(status_code=400, detail="page_count 无效")
    files = [f for f in form.getlist("files") if hasattr(f, "filename")]
    asset_ids: list[uuid.UUID] = []
    raw_ids = form.get("asset_ids")
    if raw_ids:
        try:
            if isinstance(raw_ids, str) and raw_ids.strip().startswith("["):
                parsed = json.loads(raw_ids)
                asset_ids = [uuid.UUID(str(x)) for x in parsed]
            else:
                raw = str(raw_ids)
                asset_ids = [
                    uuid.UUID(x.strip()) for x in raw.split(",") if x.strip()
                ]
        except Exception:
            raise HTTPException(status_code=400, detail="asset_ids 无效")
    return {
        "copy_id": copy_id,
        "template": template,
        "theme": theme,
        "page_count": page_count,
        "asset_ids": asset_ids,
    }, files


async def _collect_source_assets(
    files: list[UploadFile],
    asset_ids: list[uuid.UUID],
    project: StudioProject,
    user: User,
    db: AsyncSession,
) -> tuple[list[dict], list[str]]:
    """合并直接上传与素材库引用，返回 source_assets + 渲染 URL（总数 ≤8）。"""
    source_assets: list[dict] = []
    urls: list[str] = []
    if files:
        sa, u = await _consume_upload_files(files)
        source_assets.extend(sa)
        urls.extend(u)
    if asset_ids:
        sa, u = await _load_design_asset_urls(asset_ids, project, user, db)
        source_assets.extend(sa)
        urls.extend(u)
    if len(urls) > 8:
        raise HTTPException(status_code=400, detail="素材总数不能超过 8 张")
    return source_assets, urls


async def _consume_upload_files(
    files: list[UploadFile],
) -> tuple[list[dict], list[str]]:
    """校验并上传直接上传的素材图，返回 source_assets + 渲染 URL。"""
    if len(files) > _MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {_MAX_UPLOAD_FILES} 张图片")
    source_assets: list[dict] = []
    urls: list[str] = []
    for f in files:
        if f.content_type not in _ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"不支持的文件类型: {f.content_type}，"
                    f"仅允许: {', '.join(sorted(_ALLOWED_MIME))}"
                ),
            )
        data = await f.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="图片超过 10MB 限制")
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            raise HTTPException(status_code=400, detail="无法识别的图片格式")
        object_name = upload_bytes(data, f.content_type or "image/png", folder="studio")
        source_assets.append(
            {"source": "upload", "url": object_name}
        )
        urls.append(get_presigned_url(object_name))
    return source_assets, urls


@router.get(
    "/studio/decks/{deck_id}",
    response_model=StudioDeckSummary,
)
async def get_deck(
    deck_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = await _get_deck(deck_id, current_user, db)
    return _deck_response(deck)


# ============================================================
# 导出到视觉设计
# ============================================================


@router.post(
    "/studio/decks/{deck_id}/export-to-design",
    response_model=ExportToDesignResponse,
)
async def export_to_design(
    deck_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = await _get_deck(deck_id, current_user, db)
    if deck.status != "rendered" or not deck.images:
        raise HTTPException(status_code=400, detail="卡组尚未渲染完成")
    project = await _get_project(str(deck.project_id), current_user, db)

    design_project = DesignProject(
        shop_id=project.shop_id,
        title=f"内容工坊导出 · {project.title}",
        status="active",
    )
    db.add(design_project)
    await db.flush()

    asset_ids: list[uuid.UUID] = []
    for img in deck.images:
        object_name = img.get("url")
        if not object_name:
            continue
        try:
            data = get_object_bytes(object_name)
        except Exception:
            raise HTTPException(status_code=500, detail="读取卡组图片失败")
        new_object = upload_bytes(data, "image/png", folder="design")
        thumb = _make_thumb(data)
        thumb_object = upload_bytes(thumb, "image/jpeg", folder="design_thumbs")
        asset = DesignAsset(
            project_id=design_project.id,
            asset_type="photo",
            source="studio",
            status="active",
            original_url=new_object,
            thumb_url=thumb_object,
            dish_name=f"{project.title} 卡组第 {img.get('page', '')} 页",
        )
        db.add(asset)
        await db.flush()
        asset_ids.append(asset.id)

    return ExportToDesignResponse(
        design_project_id=design_project.id,
        asset_ids=asset_ids,
    )





