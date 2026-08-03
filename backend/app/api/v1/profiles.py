"""装修模块 API — Profile CRUD + AI 生成 + 图片生成/上传/裁剪 + 色板。

鉴权：所有端点校验 JWT + shop 所有权（shop -> merchant -> user）。
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.profile_agent import (
    generate_section_prompt,
    generate_variants,
    run_profile_health_check,
)
from app.ai.doubao_image import ImageGenError, generate_avatar, generate_bg_image
from app.ai.style_analyzer import analyze_style
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.core.sensitive_filter import contains_blocked
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.shop_profile import ShopProfile
from app.models.user import User
from app.schemas.profile import (
    ColorSchemePreset,
    CropRequest,
    CropResponse,
    GenerateRequest,
    GenerateResponse,
    HealthCheckRequest,
    HealthCheckResponse,
    ImageGenerateOptionsResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageOption,
    ProfileResponse,
    ProfileUpdate,
    PromptGenerateRequest,
    PromptGenerateResponse,
    RemoveGalleryImageRequest,
    SelectImageRequest,
)
from app.services.color_presets import COLOR_PRESETS
from app.services.storage import get_presigned_url, safe_get_presigned_url, upload_bytes

router = APIRouter(tags=["profiles"])


# ============================================================
# 鉴权 helper
# ============================================================

async def _verify_shop_owner(
    shop_id: str, user: User, db: AsyncSession
) -> Shop:
    """校验 shop 所有权：shop -> merchant -> user。"""
    result = await db.execute(
        select(Shop)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Shop.id == shop_id, Merchant.user_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def _get_or_create_profile(
    shop_id: str, platform: str, db: AsyncSession
) -> ShopProfile:
    """获取或新建 profile 记录。"""
    result = await db.execute(
        select(ShopProfile).where(
            ShopProfile.shop_id == shop_id, ShopProfile.platform == platform
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = ShopProfile(shop_id=shop_id, platform=platform)
        db.add(profile)
        await db.flush()
    return profile


def _upload_generated_images(
    images: list[tuple[bytes, str]],
) -> list[ImageOption]:
    """把一次生成的 4 张图全部存入 MinIO，返回可选列表。"""
    options: list[ImageOption] = []
    for img_bytes, mime in images:
        object_name = upload_bytes(img_bytes, mime, folder="profiles")
        options.append(
            ImageOption(
                object_name=object_name,
                url=get_presigned_url(object_name),
            )
        )
    return options


# ============================================================
# GET /profiles/{platform}
# ============================================================

@router.get(
    "/shops/{shop_id}/profiles/{platform}",
    response_model=ProfileResponse,
)
async def get_profile(
    shop_id: str,
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)
    profile = await _get_or_create_profile(shop_id, platform, db)

    # 生成预签名 URL（而非裸 object name）
    resp = ProfileResponse.model_validate(profile).model_dump()
    if profile.avatar_url:
        resp["avatar_url"] = safe_get_presigned_url(profile.avatar_url)
    if profile.avatar_gallery:
        avatar_options = [
            ImageOption(object_name=name, url=url).model_dump()
            for name in profile.avatar_gallery
            if (url := safe_get_presigned_url(name))
        ]
        resp["avatar_options"] = avatar_options
        avatar_url_by_name = {o["object_name"]: o["url"] for o in avatar_options}
        if profile.avatar_original_url in avatar_url_by_name:
            resp["avatar_original_url"] = avatar_url_by_name[profile.avatar_original_url]
        elif profile.avatar_original_url:
            resp["avatar_original_url"] = safe_get_presigned_url(profile.avatar_original_url)
    if profile.bg_image_url:
        resp["bg_image_url"] = safe_get_presigned_url(profile.bg_image_url)
    if profile.bg_gallery:
        bg_options = [
            ImageOption(object_name=name, url=url).model_dump()
            for name in profile.bg_gallery
            if (url := safe_get_presigned_url(name))
        ]
        resp["bg_options"] = bg_options
        bg_url_by_name = {o["object_name"]: o["url"] for o in bg_options}
        if profile.bg_original_url in bg_url_by_name:
            resp["bg_original_url"] = bg_url_by_name[profile.bg_original_url]
        elif profile.bg_original_url:
            resp["bg_original_url"] = safe_get_presigned_url(profile.bg_original_url)

    return resp


# ============================================================
# PUT /profiles/{platform} — 保存草稿（乐观锁）
# ============================================================

@router.put(
    "/shops/{shop_id}/profiles/{platform}",
    response_model=ProfileResponse,
)
async def update_profile(
    shop_id: str,
    platform: str,
    body: ProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)
    profile = await _get_or_create_profile(shop_id, platform, db)

    # 乐观锁检查
    if body.version != profile.version:
        raise HTTPException(
            status_code=409,
            detail="数据已被他人修改，请刷新后重试",
        )

    # 更新字段
    upd = body.model_dump(exclude_unset=True)
    upd.pop("version", None)

    # bio 敏感词标记
    if "bio" in upd and upd["bio"] is not None:
        bio_val = upd["bio"]
        if contains_blocked(bio_val):
            profile.bio_flagged = True
        else:
            profile.bio_flagged = False

    for k, v in upd.items():
        setattr(profile, k, v)

    profile.version += 1
    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return ProfileResponse.model_validate(profile)


# ============================================================
# POST /generate — AI 生成 4 套方案
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate",
    response_model=GenerateResponse,
)
async def generate_profiles(
    shop_id: str,
    platform: str,
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    # 频控：20s
    rate_key = f"rate_limit:generate:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=20):
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请 20 秒后重试",
        )

    # 调用 AI
    variants, raw_json = await generate_variants(
        body.category, body.style, body.price_range
    )

    # 写回 profile
    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.ai_input_category = body.category
    profile.ai_input_style = body.style
    profile.ai_input_price = body.price_range
    profile.ai_variants = {
        "variants": [v.model_dump() for v in variants]
    }
    await db.flush()

    return GenerateResponse(
        variants=variants,
        generated_at=datetime.now(timezone.utc),
    )


# ============================================================
# POST /generate-prompt — 只生成某板块的单条提示词
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate-prompt",
    response_model=PromptGenerateResponse,
)
async def generate_single_prompt(
    shop_id: str,
    platform: str,
    body: PromptGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    rate_key = f"rate_limit:generate_prompt:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=20):
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请 20 秒后重试",
        )

    prompt = await generate_section_prompt(
        body.section, body.category, body.style, body.price_range
    )

    profile = await _get_or_create_profile(shop_id, platform, db)
    field = "avatar_gen_prompt" if body.section == "avatar" else "bg_gen_prompt"
    setattr(profile, field, prompt)
    await db.flush()

    return PromptGenerateResponse(section=body.section, prompt=prompt)


# ============================================================
# POST /health-check — 主页体检（优点/不足/建议）
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/health-check",
    response_model=HealthCheckResponse,
)
async def profile_health_check(
    shop_id: str,
    platform: str,
    body: HealthCheckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    rate_key = f"rate_limit:health_check:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=20):
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请 20 秒后重试",
        )

    result = await run_profile_health_check(
        nickname=body.nickname,
        bio=body.bio,
        avatar_prompt=body.avatar_prompt,
        bg_prompt=body.bg_prompt,
        color_primary=body.color_primary,
        color_secondary=body.color_secondary,
        color_accent=body.color_accent,
        color_text=body.color_text,
        has_avatar=body.has_avatar,
        has_bg=body.has_bg,
    )

    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.health_check = result
    await db.flush()

    return HealthCheckResponse(
        **result,
        checked_at=datetime.now(timezone.utc),
    )


# ============================================================
# POST /generate-avatar — 豆包生头像
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate-avatar",
    response_model=ImageGenerateOptionsResponse,
)
async def generate_avatar_api(
    shop_id: str,
    platform: str,
    body: ImageGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    # 频控：30s
    rate_key = f"rate_limit:gen_avatar:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=30):
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请 30 秒后重试",
        )

    try:
        images = await generate_avatar(body.prompt)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    options = _upload_generated_images(images)
    object_name = options[0].object_name

    # 写入 original_url（覆盖旧值）
    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.avatar_original_url = object_name
    profile.avatar_gallery = [o.object_name for o in options]
    profile.avatar_url = None
    profile.avatar_gen_prompt = body.prompt
    await db.flush()

    return ImageGenerateOptionsResponse(
        url=options[0].url,
        prompt=body.prompt,
        options=options,
    )


# ============================================================
# POST /generate-bg-image — 豆包生背景图
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate-bg-image",
    response_model=ImageGenerateOptionsResponse,
)
async def generate_bg_image_api(
    shop_id: str,
    platform: str,
    body: ImageGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    rate_key = f"rate_limit:gen_bg:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=30):
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请 30 秒后重试",
        )

    try:
        images = await generate_bg_image(body.prompt)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    options = _upload_generated_images(images)
    object_name = options[0].object_name

    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.bg_original_url = object_name
    profile.bg_gallery = [o.object_name for o in options]
    profile.bg_image_url = None
    profile.bg_gen_prompt = body.prompt
    await db.flush()

    return ImageGenerateOptionsResponse(
        url=options[0].url,
        prompt=body.prompt,
        options=options,
    )


# ============================================================
# POST /upload-avatar /upload-bg-image — 手动上传图片
# ============================================================

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


async def _handle_upload(
    file: UploadFile,
    shop_id: str,
    platform: str,
    field_original: str,
    field_prompt: str,
    field_gallery: str,
    db: AsyncSession,
    current_user: User,
) -> ImageGenerateResponse:
    """通用上传处理。"""
    await _verify_shop_owner(shop_id, current_user, db)

    # MIME 校验
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}，仅允许: {', '.join(_ALLOWED_MIME)}",
        )

    # 读取 + 大小校验
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    # PIL 二次验证
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的图片格式")

    object_name = upload_bytes(data, file.content_type or "image/png", folder="profiles")

    profile = await _get_or_create_profile(shop_id, platform, db)
    setattr(profile, field_original, object_name)
    setattr(profile, field_gallery, None)
    if field_prompt:
        setattr(profile, field_prompt, None)  # 上传覆盖 prompt
    await db.flush()

    return ImageGenerateResponse(
        url=get_presigned_url(object_name),
        prompt="(手动上传)",
    )


async def _read_ref_image(
    ref_image: UploadFile | None,
) -> tuple[bytes | None, str]:
    """读取并校验参考图，返回 (data, mime)。"""
    if not ref_image:
        return None, "image/png"

    if ref_image.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                f"参考图格式不支持: {ref_image.content_type}，"
                f"仅允许: {', '.join(_ALLOWED_MIME)}"
            ),
        )

    data = await ref_image.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="参考图超过 10MB")
    return data, ref_image.content_type or "image/png"


@router.post(
    "/shops/{shop_id}/profiles/{platform}/upload-avatar",
    response_model=ImageGenerateResponse,
)
async def upload_avatar(
    shop_id: str,
    platform: str,
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _handle_upload(
        file, shop_id, platform,
        "avatar_original_url", "avatar_gen_prompt", "avatar_gallery",
        db, current_user,
    )


@router.post(
    "/shops/{shop_id}/profiles/{platform}/upload-bg-image",
    response_model=ImageGenerateResponse,
)
async def upload_bg_image(
    shop_id: str,
    platform: str,
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _handle_upload(
        file, shop_id, platform,
        "bg_original_url", "bg_gen_prompt", "bg_gallery",
        db, current_user,
    )


# ============================================================
# POST /crop-avatar /crop-bg-image — 裁剪
# ============================================================

async def _handle_crop(
    body: CropRequest,
    shop_id: str,
    platform: str,
    field_url: str,
    field_original: str,
    db: AsyncSession,
    current_user: User,
) -> CropResponse:
    """通用裁剪处理。"""
    await _verify_shop_owner(shop_id, current_user, db)

    profile = await _get_or_create_profile(shop_id, platform, db)
    original = getattr(profile, field_original, None)
    if not original:
        raise HTTPException(
            status_code=400,
            detail="请先生成或上传原图",
        )

    # 解码 base64（已在 Schema 层校验大小 <=10MB）
    b64_data = body.image_base64
    if "," in b64_data and b64_data.startswith("data:"):
        b64_data = b64_data.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 base64 编码")

    # PIL 验证
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的裁剪图片")

    # 上传裁剪结果（按实际格式存储，避免 JPEG 字节被标记为 PNG）
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            mime = "image/jpeg" if img.format in ("JPEG", "MPO") else "image/png"
    except Exception:
        mime = "image/png"
    object_name = upload_bytes(img_bytes, mime, folder="profiles")

    # 写入裁剪 URL（不覆盖 original_url）
    setattr(profile, field_url, object_name)
    await db.flush()

    return CropResponse(url=get_presigned_url(object_name))


@router.post(
    "/shops/{shop_id}/profiles/{platform}/crop-avatar",
    response_model=CropResponse,
)
async def crop_avatar(
    shop_id: str,
    platform: str,
    body: CropRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _handle_crop(
        body, shop_id, platform,
        "avatar_url", "avatar_original_url",
        db, current_user,
    )


@router.post(
    "/shops/{shop_id}/profiles/{platform}/crop-bg-image",
    response_model=CropResponse,
)
async def crop_bg_image(
    shop_id: str,
    platform: str,
    body: CropRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _handle_crop(
        body, shop_id, platform,
        "bg_image_url", "bg_original_url",
        db, current_user,
    )


# ============================================================
# POST /generate-avatar-with-ref — 带参考图的头像生成
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate-avatar-with-ref",
    response_model=ImageGenerateOptionsResponse,
)
async def generate_avatar_with_ref(
    shop_id: str,
    platform: str,
    prompt: str = Form(...),
    ref_image: UploadFile | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    # 敏感词检查
    if contains_blocked(prompt):
        raise HTTPException(status_code=422, detail="prompt 包含敏感词")

    # 频控
    rate_key = f"rate_limit:gen_avatar:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=30):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 30 秒后重试")

    ref_data, ref_mime = await _read_ref_image(ref_image)
    try:
        images = await generate_avatar(prompt, ref_data, ref_mime)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    options = _upload_generated_images(images)
    object_name = options[0].object_name

    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.avatar_original_url = object_name
    profile.avatar_gallery = [o.object_name for o in options]
    profile.avatar_url = None
    profile.avatar_gen_prompt = prompt
    await db.flush()

    return ImageGenerateOptionsResponse(
        url=options[0].url,
        prompt=prompt,
        options=options,
    )


# ============================================================
# POST /generate-bg-image-with-ref — 带参考图的背景生成
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/generate-bg-image-with-ref",
    response_model=ImageGenerateOptionsResponse,
)
async def generate_bg_image_with_ref(
    shop_id: str,
    platform: str,
    prompt: str = Form(...),
    ref_image: UploadFile | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    if contains_blocked(prompt):
        raise HTTPException(status_code=422, detail="prompt 包含敏感词")

    rate_key = f"rate_limit:gen_bg:{shop_id}:{platform}"
    if not await check_rate_limit(rate_key, ttl_seconds=30):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 30 秒后重试")

    ref_data, ref_mime = await _read_ref_image(ref_image)
    try:
        images = await generate_bg_image(prompt, ref_data, ref_mime)
    except ImageGenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    options = _upload_generated_images(images)
    object_name = options[0].object_name

    profile = await _get_or_create_profile(shop_id, platform, db)
    profile.bg_original_url = object_name
    profile.bg_gallery = [o.object_name for o in options]
    profile.bg_image_url = None
    profile.bg_gen_prompt = prompt
    await db.flush()

    return ImageGenerateOptionsResponse(
        url=options[0].url,
        prompt=prompt,
        options=options,
    )


async def _select_gallery_image(
    shop_id: str,
    platform: str,
    body: SelectImageRequest,
    field_gallery: str,
    field_original: str,
    field_url: str,
    field_prompt: str,
    db: AsyncSession,
    current_user: User,
) -> ImageGenerateResponse:
    """从本次生成的 4 张图中选一张作为当前原图。"""
    await _verify_shop_owner(shop_id, current_user, db)
    profile = await _get_or_create_profile(shop_id, platform, db)
    gallery = getattr(profile, field_gallery) or []
    if body.object_name not in gallery:
        raise HTTPException(
            status_code=400,
            detail="图片不在本次生成结果中，请重新生成",
        )

    setattr(profile, field_original, body.object_name)
    setattr(profile, field_url, None)
    await db.flush()

    return ImageGenerateResponse(
        url=get_presigned_url(body.object_name),
        prompt=getattr(profile, field_prompt) or "",
    )


@router.post(
    "/shops/{shop_id}/profiles/{platform}/select-avatar",
    response_model=ImageGenerateResponse,
)
async def select_avatar(
    shop_id: str,
    platform: str,
    body: SelectImageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _select_gallery_image(
        shop_id,
        platform,
        body,
        "avatar_gallery",
        "avatar_original_url",
        "avatar_url",
        "avatar_gen_prompt",
        db,
        current_user,
    )


@router.post(
    "/shops/{shop_id}/profiles/{platform}/select-bg-image",
    response_model=ImageGenerateResponse,
)
async def select_bg_image(
    shop_id: str,
    platform: str,
    body: SelectImageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _select_gallery_image(
        shop_id,
        platform,
        body,
        "bg_gallery",
        "bg_original_url",
        "bg_image_url",
        "bg_gen_prompt",
        db,
        current_user,
    )


@router.post(
    "/shops/{shop_id}/profiles/{platform}/remove-gallery-image",
    response_model=list[ImageOption],
)
async def remove_gallery_image(
    shop_id: str,
    platform: str,
    body: RemoveGalleryImageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从本次生成结果中移除一张图，若为当前原图则一并清除选择。"""
    await _verify_shop_owner(shop_id, current_user, db)
    profile = await _get_or_create_profile(shop_id, platform, db)

    gallery_field = "avatar_gallery" if body.section == "avatar" else "bg_gallery"
    original_field = "avatar_original_url" if body.section == "avatar" else "bg_original_url"
    url_field = "avatar_url" if body.section == "avatar" else "bg_image_url"

    gallery = getattr(profile, gallery_field) or []
    if body.object_name not in gallery:
        raise HTTPException(
            status_code=400,
            detail="图片不在本次生成结果中",
        )

    gallery = [name for name in gallery if name != body.object_name]
    setattr(profile, gallery_field, gallery or None)
    if getattr(profile, original_field) == body.object_name:
        setattr(profile, original_field, None)
        setattr(profile, url_field, None)
    await db.flush()

    return [
        ImageOption(object_name=name, url=get_presigned_url(name))
        for name in gallery
    ]


# ============================================================
# POST /analyze-style — XHS 截图风格分析 → 复刻同款
# ============================================================

@router.post(
    "/shops/{shop_id}/profiles/{platform}/analyze-style",
)
async def analyze_style_endpoint(
    shop_id: str,
    platform: str,
    image: UploadFile,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)

    data = await image.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片超过 10MB")

    result = await analyze_style(data, image.content_type or "image/png")
    return result

# ============================================================
# GET /color-schemes — 色板预设
# ============================================================

@router.get(
    "/color-schemes",
    response_model=list[ColorSchemePreset],
)
async def get_color_schemes():
    return COLOR_PRESETS


