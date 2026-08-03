"""视觉设计模块 API — 项目/素材/菜单 CRUD + AI 生成候选 + 一键美化 + 渲染。

鉴权：所有端点校验 JWT + shop 所有权（project -> shop -> merchant -> user）。
"""
from __future__ import annotations

import base64
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.doubao_image import ImageGenError, generate_edited
from app.ai.design_prompt import generate_beautify_prompt
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.core.sensitive_filter import contains_blocked
from app.models.design_asset import DesignAsset
from app.models.design_project import DesignProject
from app.models.menu_design import MenuDesign
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.user import User
from app.schemas.design import (
    AiBeautifyRequest,
    AssetCandidate,
    BeautifyPromptRequest,
    BeautifyPromptResponse,
    BeautifyRequest,
    ConfirmResponse,
    DesignAssetResponse,
    DesignAssetUpdate,
    DesignProjectCreate,
    DesignProjectResponse,
    DesignProjectUpdate,
    EditRequest,
    GenerateCandidatesResponse,
    MenuCreate,
    MenuItemInput,
    MenuResponse,
    MenuUpdate,
    RenderRequest,
    RenderResponse,
    SaveRequest,
)
from app.services.design_beautify import auto_beautify
from app.services.menu_render import render_menu, resolve_item
from app.services.storage import (
    get_object_bytes,
    get_presigned_url,
    safe_get_presigned_url,
    upload_bytes,
)

router = APIRouter(tags=["design"])

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_KNOWN_TEMPLATES = {"xhs_menu_01": "xhs", "a4_menu_01": "a4"}


# ============================================================
# 鉴权与资源 helper
# ============================================================


async def _verify_shop_owner(
    shop_id: str, user: User, db: AsyncSession
) -> Shop:
    result = await db.execute(
        select(Shop)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Shop.id == shop_id, Merchant.user_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def _get_project(
    project_id: str, user: User, db: AsyncSession
) -> DesignProject:
    result = await db.execute(
        select(DesignProject)
        .join(Shop, DesignProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(DesignProject.id == project_id, Merchant.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_project_asset(
    project: DesignProject,
    asset_id: str,
    db: AsyncSession,
) -> DesignAsset:
    result = await db.execute(
        select(DesignAsset).where(
            DesignAsset.id == asset_id,
            DesignAsset.project_id == project.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


async def _get_project_menu(
    project: DesignProject,
    menu_id: str,
    db: AsyncSession,
) -> MenuDesign:
    result = await db.execute(
        select(MenuDesign).where(
            MenuDesign.id == menu_id,
            MenuDesign.project_id == project.id,
        )
    )
    menu = result.scalar_one_or_none()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    return menu


def _asset_response(asset: DesignAsset) -> dict:
    resp = DesignAssetResponse.model_validate(asset).model_dump()
    for field in ("original_url", "processed_url", "thumb_url"):
        if resp.get(field):
            resp[field] = safe_get_presigned_url(resp[field]) or resp[field]
    return resp


def _menu_response(menu: MenuDesign) -> dict:
    resp = MenuResponse.model_validate(menu).model_dump()
    if resp.get("output_url"):
        resp["output_url"] = (
            safe_get_presigned_url(resp["output_url"]) or resp["output_url"]
        )
    return resp


def _touch(asset_or_menu) -> None:
    asset_or_menu.updated_at = datetime.now(timezone.utc)


# ============================================================
# 图片读取/校验 helper
# ============================================================


async def _read_ref_image(
    ref_image: UploadFile | None,
) -> tuple[bytes | None, str]:
    if not ref_image:
        return None, "image/png"
    if ref_image.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                f"参考图格式不支持: {ref_image.content_type}，"
                f"仅允许: {', '.join(sorted(_ALLOWED_MIME))}"
            ),
        )
    data = await ref_image.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="参考图超过 10MB")
    return data, ref_image.content_type or "image/png"


def _decode_image_base64(image_base64: str) -> tuple[bytes, str]:
    if "," in image_base64 and image_base64.startswith("data:"):
        image_base64 = image_base64.split(",", 1)[1]
    try:
        data = base64.b64decode(image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 base64 编码")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            fmt = img.format
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的图片格式")
    mime = "image/jpeg" if fmt in ("JPEG", "MPO") else "image/png"
    return data, mime


def _asset_source_bytes(asset: DesignAsset) -> bytes:
    source = asset.processed_url or asset.original_url
    if not source:
        raise HTTPException(status_code=400, detail="素材缺少源图")
    try:
        return get_object_bytes(source)
    except Exception:
        raise HTTPException(status_code=502, detail="源图读取失败，请重新上传")


def _coerce_template(menu_type: str, template_id: str) -> str:
    if template_id not in _KNOWN_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"未知模板: {template_id}")
    if _KNOWN_TEMPLATES[template_id] != menu_type:
        template_id = "a4_menu_01" if menu_type == "a4" else "xhs_menu_01"
    return template_id


def _item_asset_id(item) -> str:
    if isinstance(item, MenuItemInput):
        return str(item.asset_id)
    return str(item["asset_id"])


async def _validate_menu_items(
    items: list,
    project_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    if not items:
        return
    asset_ids = list({_item_asset_id(it) for it in items})
    result = await db.execute(
        select(DesignAsset).where(DesignAsset.id.in_(asset_ids))
    )
    assets = {str(a.id): a for a in result.scalars().all()}
    for item in items:
        asset = assets.get(_item_asset_id(item))
        if asset is None or str(asset.project_id) != str(project_id):
            raise HTTPException(
                status_code=400,
                detail="菜单 item 的 asset_id 不属于当前项目",
            )
        if asset.status != "active":
            raise HTTPException(
                status_code=400,
                detail="菜单 item 的素材必须为 active",
            )


def _items_for_storage(items: list[MenuItemInput]) -> list[dict]:
    return [item.model_dump(mode="json") for item in items]


def _rate_key(action: str, user: User, shop_id: uuid.UUID) -> str:
    return f"rate_limit:design_{action}:{user.id}:{shop_id}"


# ============================================================
# 项目 CRUD
# ============================================================


@router.get(
    "/design-projects",
    response_model=list[DesignProjectResponse],
)
async def list_projects(
    shop_id: str = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)
    stmt = select(DesignProject).where(DesignProject.shop_id == shop_id)
    if status_filter:
        stmt = stmt.where(DesignProject.status == status_filter)
    stmt = stmt.order_by(DesignProject.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/design-projects",
    response_model=DesignProjectResponse,
)
async def create_project(
    body: DesignProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(str(body.shop_id), current_user, db)
    project = DesignProject(
        shop_id=body.shop_id,
        title=body.title,
        status=body.status,
    )
    db.add(project)
    await db.flush()
    return project


@router.get(
    "/design-projects/{project_id}",
    response_model=DesignProjectResponse,
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_project(project_id, current_user, db)


@router.patch(
    "/design-projects/{project_id}",
    response_model=DesignProjectResponse,
)
async def update_project(
    project_id: str,
    body: DesignProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    _touch(project)
    await db.flush()
    return project


@router.delete("/design-projects/{project_id}")
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
# 素材
# ============================================================


@router.get(
    "/design-projects/{project_id}/assets",
    response_model=list[DesignAssetResponse],
)
async def list_assets(
    project_id: str,
    status_filter: str | None = Query(None, alias="status"),
    asset_type: str | None = Query(None),
    include_derived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project(project_id, current_user, db)
    stmt = select(DesignAsset).where(DesignAsset.project_id == project_id)
    if not include_derived:
        stmt = stmt.where(DesignAsset.derived_from_asset_id.is_(None))
    if status_filter:
        stmt = stmt.where(DesignAsset.status == status_filter)
    if asset_type:
        stmt = stmt.where(DesignAsset.asset_type == asset_type)
    stmt = stmt.order_by(DesignAsset.created_at.desc())
    result = await db.execute(stmt)
    return [_asset_response(a) for a in result.scalars().all()]


@router.post(
    "/design-projects/{project_id}/assets",
    response_model=DesignAssetResponse,
)
async def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    asset_type: str = Form("photo"),
    dish_name: str | None = Form(None),
    price: str | None = Form(None),
    tagline: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    if asset_type not in ("dish", "logo", "photo"):
        raise HTTPException(status_code=400, detail=f"未知素材类型: {asset_type}")
    if dish_name and contains_blocked(dish_name):
        raise HTTPException(status_code=422, detail="dish_name 包含敏感词")
    if tagline and contains_blocked(tagline):
        raise HTTPException(status_code=422, detail="tagline 包含敏感词")
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的文件类型: {file.content_type}，"
                f"仅允许: {', '.join(sorted(_ALLOWED_MIME))}"
            ),
        )
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的图片格式")

    parsed_price: Decimal | None = None
    if price:
        try:
            parsed_price = Decimal(price)
        except InvalidOperation:
            raise HTTPException(status_code=400, detail="price 格式无效")

    object_name = upload_bytes(data, file.content_type or "image/png", folder="design")
    asset = DesignAsset(
        project_id=project.id,
        asset_type=asset_type,
        source="upload",
        status="active",
        original_url=object_name,
        dish_name=dish_name,
        price=parsed_price,
        tagline=tagline,
    )
    db.add(asset)
    await db.flush()
    return _asset_response(asset)


@router.patch(
    "/design-projects/{project_id}/assets/{asset_id}",
    response_model=DesignAssetResponse,
)
async def update_asset(
    project_id: str,
    asset_id: str,
    body: DesignAssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    _touch(asset)
    await db.flush()
    return _asset_response(asset)


@router.delete("/design-projects/{project_id}/assets/{asset_id}")
async def delete_asset(
    project_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)

    menus = await db.execute(
        select(MenuDesign).where(MenuDesign.project_id == project.id)
    )
    for menu in menus.scalars().all():
        for item in menu.items or []:
            if _item_asset_id(item) == str(asset.id):
                raise HTTPException(
                    status_code=409,
                    detail="素材已被菜单引用，无法删除",
                )

    await db.delete(asset)
    await db.flush()
    return {"ok": True}


# ============================================================
# AI 生成候选
# ============================================================


@router.post(
    "/design-projects/{project_id}/assets/generate",
    response_model=GenerateCandidatesResponse,
)
async def generate_assets(
    project_id: str,
    prompt: str = Form(...),
    ref_image: UploadFile | None = None,
    asset_type: str = Form("photo"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    if contains_blocked(prompt):
        raise HTTPException(status_code=422, detail="prompt 包含敏感词")
    if asset_type not in ("dish", "logo", "photo"):
        raise HTTPException(status_code=400, detail=f"未知素材类型: {asset_type}")
    if not await check_rate_limit(
        _rate_key("generate", current_user, project.shop_id), ttl_seconds=60
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后重试")

    ref_data, ref_mime = await _read_ref_image(ref_image)
    try:
        images = await generate_edited(prompt, ref_data, ref_mime)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    batch_id = uuid.uuid4()
    candidates: list[AssetCandidate] = []
    for img_bytes, mime in images:
        object_name = upload_bytes(img_bytes, mime, folder="design")
        asset = DesignAsset(
            project_id=project.id,
            asset_type=asset_type,
            source="ai",
            status="pending",
            batch_id=batch_id,
            original_url=object_name,
        )
        db.add(asset)
        await db.flush()
        candidates.append(
            AssetCandidate(
                aid=asset.id,
                url=get_presigned_url(object_name),
                batch_id=batch_id,
            )
        )
    return GenerateCandidatesResponse(batch_id=batch_id, candidates=candidates)


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/confirm",
    response_model=ConfirmResponse,
)
async def confirm_asset(
    project_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    if asset.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="候选已处理，重复确认无效",
        )
    if not asset.batch_id:
        raise HTTPException(status_code=409, detail="候选缺少批次信息")

    batch_id = asset.batch_id
    result = await db.execute(
        select(DesignAsset).where(
            DesignAsset.project_id == project.id,
            DesignAsset.batch_id == batch_id,
        )
    )
    same_batch = result.scalars().all()
    if not same_batch:
        raise HTTPException(status_code=409, detail="候选批次为空")

    discarded: list[uuid.UUID] = []
    for candidate in same_batch:
        if candidate.id == asset.id:
            candidate.status = "active"
        else:
            candidate.status = "discarded"
            discarded.append(candidate.id)
        _touch(candidate)
    await db.flush()
    return ConfirmResponse(
        batch_id=batch_id,
        active_aid=asset.id,
        discarded_aids=discarded,
    )


# ============================================================
# 一键美化 / 派生编辑 / 保存
# ============================================================


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/beautify",
    response_model=DesignAssetResponse,
)
async def beautify_asset(
    project_id: str,
    asset_id: str,
    body: BeautifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    if not await check_rate_limit(
        _rate_key("beautify", current_user, project.shop_id), ttl_seconds=30
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 30 秒后重试")

    data = _asset_source_bytes(asset)
    out = auto_beautify(
        data,
        mode=body.mode,
        brightness=body.brightness,
        contrast=body.contrast,
        saturation=body.saturation,
    )
    object_name = upload_bytes(out, "image/jpeg", folder="design")
    asset.processed_url = object_name
    asset.beauty_config = body.model_dump()
    _touch(asset)
    await db.flush()
    return _asset_response(asset)


_AI_BEAUTIFY_DEFAULT_PROMPT = (
    "对参考图进行高级美食摄影美化：提升菜品的光泽与质感，"
    "优化光影层次，增强画面的食欲感和氛围，"
    "保留菜品主体、形状、颜色与整体构图，不要改变菜品结构。"
)


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/ai-beautify",
    response_model=GenerateCandidatesResponse,
)
async def ai_beautify(
    project_id: str,
    asset_id: str,
    body: AiBeautifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 一键美化：豆包生成 4 张候选，带参考图并记录派生来源。"""
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    prompt = body.prompt or _AI_BEAUTIFY_DEFAULT_PROMPT
    return await _generate_derived_candidates(
        project, asset, prompt, current_user, db, rate_action="ai_beautify"
    )


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/ai-beautify/prompt",
    response_model=BeautifyPromptResponse,
)
async def generate_ai_beautify_prompt(
    project_id: str,
    asset_id: str,
    body: BeautifyPromptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 生成一键美化提示词，用户可编辑后再调用 ai-beautify。"""
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    if not await check_rate_limit(
        _rate_key("beautify_prompt", current_user, project.shop_id),
        ttl_seconds=20,
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后重试")
    try:
        prompt = await generate_beautify_prompt(
            focus=body.focus,
            dish_name=body.dish_name or asset.dish_name,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="提示词生成失败，请稍后重试")
    return BeautifyPromptResponse(prompt=prompt)


async def _generate_derived_candidates(
    project: DesignProject,
    asset: DesignAsset,
    prompt: str,
    user: User,
    db: AsyncSession,
    rate_action: str = "edit",
) -> GenerateCandidatesResponse:
    if not await check_rate_limit(
        _rate_key(rate_action, user, project.shop_id), ttl_seconds=60
    ):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后重试")
    data = _asset_source_bytes(asset)
    try:
        images = await generate_edited(prompt, data, "image/png")
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    batch_id = uuid.uuid4()
    candidates: list[AssetCandidate] = []
    for img_bytes, mime in images:
        object_name = upload_bytes(img_bytes, mime, folder="design")
        candidate = DesignAsset(
            project_id=project.id,
            asset_type=asset.asset_type,
            source="ai",
            status="pending",
            batch_id=batch_id,
            derived_from_asset_id=asset.id,
            original_url=object_name,
        )
        db.add(candidate)
        await db.flush()
        candidates.append(
            AssetCandidate(
                aid=candidate.id,
                url=get_presigned_url(object_name),
                batch_id=batch_id,
            )
        )
    return GenerateCandidatesResponse(batch_id=batch_id, candidates=candidates)


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/bg-replace",
    response_model=GenerateCandidatesResponse,
)
async def bg_replace(
    project_id: str,
    asset_id: str,
    body: EditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    return await _generate_derived_candidates(
        project, asset, body.prompt, current_user, db
    )


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/enhance",
    response_model=GenerateCandidatesResponse,
)
async def enhance_asset(
    project_id: str,
    asset_id: str,
    body: EditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    return await _generate_derived_candidates(
        project, asset, body.prompt, current_user, db
    )


@router.post(
    "/design-projects/{project_id}/assets/{asset_id}/save",
    response_model=DesignAssetResponse,
)
async def save_asset(
    project_id: str,
    asset_id: str,
    body: SaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    asset = await _get_project_asset(project, asset_id, db)
    data, mime = _decode_image_base64(body.image_base64)
    object_name = upload_bytes(data, mime, folder="design")
    asset.processed_url = object_name
    if body.edit_stack is not None:
        asset.edit_stack = body.edit_stack
    if body.beauty_config is not None:
        asset.beauty_config = body.beauty_config

    # 折叠派生候选：同项目 active 且 derived_from=当前 aid 的记录置为 discarded
    result = await db.execute(
        select(DesignAsset).where(
            DesignAsset.project_id == project.id,
            DesignAsset.status == "active",
            DesignAsset.derived_from_asset_id == asset.id,
        )
    )
    for candidate in result.scalars().all():
        candidate.status = "discarded"
        _touch(candidate)
    _touch(asset)
    await db.flush()
    return _asset_response(asset)


# ============================================================
# 菜单
# ============================================================


@router.post(
    "/design-projects/{project_id}/menus",
    response_model=MenuResponse,
)
async def create_menu(
    project_id: str,
    body: MenuCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    await _validate_menu_items(body.items, project.id, db)
    template_id = _coerce_template(body.menu_type, body.template_id)
    menu = MenuDesign(
        project_id=project.id,
        menu_type=body.menu_type,
        template_id=template_id,
        shop_name=body.shop_name,
        logo_url=body.logo_url,
        color_scheme=(
            body.color_scheme.model_dump() if body.color_scheme else None
        ),
        items=_items_for_storage(body.items),
        status="draft",
        version=0,
    )
    db.add(menu)
    await db.flush()
    return _menu_response(menu)


@router.get(
    "/design-projects/{project_id}/menus",
    response_model=list[MenuResponse],
)
async def list_menus(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_project(project_id, current_user, db)
    result = await db.execute(
        select(MenuDesign)
        .where(MenuDesign.project_id == project_id)
        .order_by(MenuDesign.created_at.desc())
    )
    return [_menu_response(m) for m in result.scalars().all()]


@router.get(
    "/design-projects/{project_id}/menus/{menu_id}",
    response_model=MenuResponse,
)
async def get_menu(
    project_id: str,
    menu_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    menu = await _get_project_menu(project, menu_id, db)
    return _menu_response(menu)


@router.patch(
    "/design-projects/{project_id}/menus/{menu_id}",
    response_model=MenuResponse,
)
async def update_menu(
    project_id: str,
    menu_id: str,
    body: MenuUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    menu = await _get_project_menu(project, menu_id, db)
    if body.version != menu.version:
        raise HTTPException(
            status_code=409,
            detail="菜单已被他人修改，请刷新后重试",
        )

    updates = body.model_dump(exclude_unset=True)
    updates.pop("version", None)
    if updates.get("items") is not None:
        await _validate_menu_items(updates["items"], project.id, db)
        updates["items"] = [
            item.model_dump(mode="json") for item in updates["items"]
        ]
    if updates.get("color_scheme") is not None:
        updates["color_scheme"] = updates["color_scheme"].model_dump()
    if updates.get("menu_type") or updates.get("template_id"):
        menu_type = updates.get("menu_type") or menu.menu_type
        template_id = updates.get("template_id") or menu.template_id
        updates["template_id"] = _coerce_template(menu_type, template_id)

    for key, value in updates.items():
        setattr(menu, key, value)
    menu.version += 1
    _touch(menu)
    await db.flush()
    return _menu_response(menu)


@router.post(
    "/design-projects/{project_id}/menus/{menu_id}/render",
    response_model=RenderResponse,
)
async def render_menu_api(
    project_id: str,
    menu_id: str,
    body: RenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    menu = await _get_project_menu(project, menu_id, db)
    if body.version != menu.version:
        raise HTTPException(
            status_code=409,
            detail="菜单版本不匹配，请刷新后重试",
        )

    items = menu.items or []
    await _validate_menu_items(items, project.id, db)
    asset_ids = list({_item_asset_id(it) for it in items})
    result = await db.execute(
        select(DesignAsset).where(DesignAsset.id.in_(asset_ids))
    )
    assets = {str(a.id): a for a in result.scalars().all()}

    resolved_items: list[dict] = []
    asset_images: dict[str, bytes] = {}
    for item in items:
        asset = assets[_item_asset_id(item)]
        resolved_items.append(resolve_item(item, asset))
        source = asset.processed_url or asset.original_url
        if not source:
            raise HTTPException(status_code=400, detail="菜单素材缺少图片")
        try:
            asset_images[str(asset.id)] = get_object_bytes(source)
        except Exception:
            raise HTTPException(status_code=502, detail="菜单素材图片读取失败")

    config = {
        "template_id": menu.template_id,
        "shop_name": menu.shop_name or "本店菜单",
        "color_scheme": menu.color_scheme or {},
        "items": resolved_items,
    }
    try:
        png_bytes = render_menu(config, asset_images)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    object_name = upload_bytes(png_bytes, "image/png", folder="design_menus")
    menu.output_url = object_name
    menu.status = "rendered"
    menu.version += 1
    _touch(menu)
    await db.flush()
    return RenderResponse(
        id=menu.id,
        output_url=get_presigned_url(object_name),
        version=menu.version,
    )
