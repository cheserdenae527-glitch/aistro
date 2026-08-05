"""团购工坊模块 API — 项目/菜品/竞品 CRUD + AI 方案生成 + 平台文案 + 导出到视觉设计。

鉴权：所有端点校验 JWT + shop 所有权（project -> shop -> merchant -> user）。
流程遵循 SPEC-DEALS v0.2 / PLAN-DEALS G1：
- regenerate 语义：旧批次全部 is_archived=true（不删除），新生成 3 款为当前活跃批次
- 频控：generate / copy 各 20s，仅生成成功时计入（422 敏感词失败 / AI 格式错误不占窗口）
- 毛利：gross/net 按 SPEC 公式计算，负 net_margin 只警示不硬拒
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import openai
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.deal_agent import DealAgent, DealAgentError
from app.ai.deal_copy_agent import DealCopyAgent, DealCopyAgentError
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import peek_rate_limit, set_rate_limit
from app.core.sensitive_filter import contains_blocked
from app.models.competitor_deal import CompetitorDeal
from app.models.deal_item import DealItem
from app.models.deal_project import DealProject
from app.models.deal_scheme import DealScheme
from app.models.deal_scheme_copy import DealSchemeCopy
from app.models.design_asset import DesignAsset
from app.models.design_project import DesignProject
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.user import User
from app.schemas.deals import (
    CompetitorDealCreate,
    CompetitorDealUpdate,
    CompetitorDealListResponse,
    CompetitorDealOut,
    DealCopyGenerateRequest,
    DealCopyOut,
    DealItemCreate,
    DealItemListResponse,
    DealItemOut,
    DealItemUpdate,
    DealProjectCreate,
    DealProjectListResponse,
    DealProjectResponse,
    DealProjectUpdate,
    DealSchemeOut,
    ExportToDesignRequest,
    ExportToDesignResponse,
    SchemeGenerateResponse,
    SchemeUpdateRequest,
)
from app.services.deals import build_margin_estimate, platform_commission_rate

router = APIRouter(tags=["deals"])

_RATE_TTL = 20
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


# ============================================================
# 鉴权与资源 helper
# ============================================================


async def _verify_shop_owner(shop_id: str, user: User, db: AsyncSession) -> Shop:
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


async def _get_project(project_id: str, user: User, db: AsyncSession) -> DealProject:
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(DealProject)
        .join(Shop, DealProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(DealProject.id == project_uuid, Merchant.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_item(project: DealProject, item_id: str, db: AsyncSession) -> DealItem:
    try:
        item_uuid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Item not found")
    result = await db.execute(
        select(DealItem).where(DealItem.id == item_uuid, DealItem.project_id == project.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


async def _get_competitor(
    project: DealProject, competitor_id: str, db: AsyncSession
) -> CompetitorDeal:
    try:
        c_uuid = uuid.UUID(competitor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Competitor not found")
    result = await db.execute(
        select(CompetitorDeal).where(
            CompetitorDeal.id == c_uuid, CompetitorDeal.project_id == project.id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return row


async def _get_scheme(project: DealProject, scheme_id: str, db: AsyncSession) -> DealScheme:
    try:
        scheme_uuid = uuid.UUID(scheme_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Scheme not found")
    result = await db.execute(
        select(DealScheme).where(
            DealScheme.id == scheme_uuid, DealScheme.project_id == project.id
        )
    )
    scheme = result.scalar_one_or_none()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return scheme


async def _scheme_copies(db: AsyncSession, scheme_id: uuid.UUID) -> list[DealSchemeCopy]:
    rows = (
        await db.execute(
            select(DealSchemeCopy)
            .where(DealSchemeCopy.scheme_id == scheme_id)
            .order_by(DealSchemeCopy.created_at)
        )
    ).scalars().all()
    return list(rows)


def _scheme_out(scheme: DealScheme, copies: list[DealSchemeCopy]) -> DealSchemeOut:
    out = DealSchemeOut.model_validate(scheme)
    out.copies = [DealCopyOut.model_validate(c) for c in copies]
    return out


def _scheme_context(scheme: DealScheme) -> dict:
    return {
        "scheme_type": scheme.scheme_type,
        "title": scheme.title,
        "description": scheme.description,
        "original_price": float(scheme.original_price),
        "deal_price": float(scheme.deal_price),
        "items": scheme.items or [],
    }


def _resolve_scheme(
    raw: dict,
    items_by_id: dict[uuid.UUID, DealItem],
    commission: float,
) -> dict:
    """把 AI 原始方案落成快照 items + 毛利估算。

    快照语义：name/sale_price 以 deal_items 实时值为准；cost_price 优先取真实成本，
    缺失时用 AI 估算并在 note 标注；此后菜品清单修改不影响已生成方案。
    """
    snapshot: list[dict] = []
    estimated = False
    for it in raw["items"]:
        item = items_by_id.get(uuid.UUID(it["item_id"]))
        if item is None:
            raise DealAgentError("LLM 引用了不属于该项目的菜品")
        cost = item.cost_price
        if cost is None:
            est = it.get("cost_price")
            if est is None or est <= 0:
                raise DealAgentError("LLM 对无成本菜品缺少估算成本")
            cost = est
            estimated = True
        snapshot.append(
            {
                "item_id": str(item.id),
                "name": item.name,
                "qty": it["qty"],
                "sale_price": float(item.sale_price),
                "cost_price": float(cost),
            }
        )
    cost_estimate = sum(
        (Decimal(str(si["cost_price"])) * si["qty"]) for si in snapshot
    )
    margin = build_margin_estimate(
        raw["deal_price"],
        cost_estimate,
        commission,
        estimated=estimated,
        scheme_type=raw["scheme_type"],
    )
    return {
        "scheme_type": raw["scheme_type"],
        "title": raw["title"],
        "description": raw["description"],
        "items": snapshot,
        "original_price": raw["original_price"],
        "deal_price": raw["deal_price"],
        "cost_estimate": cost_estimate,
        "margin_estimate": margin,
    }


# ============================================================
# 项目 CRUD
# ============================================================


@router.post("/deal-projects", response_model=DealProjectResponse)
async def create_project(
    body: DealProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(str(body.shop_id), current_user, db)
    project = DealProject(
        shop_id=body.shop_id,
        title=body.title,
        platform=body.platform,
        price_band=body.price_band,
    )
    db.add(project)
    await db.flush()
    return project


@router.get("/deal-projects", response_model=DealProjectListResponse)
async def list_projects(
    shop_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = (
        select(DealProject)
        .join(Shop, DealProject.shop_id == Shop.id)
        .join(Merchant, Shop.merchant_id == Merchant.id)
        .where(Merchant.user_id == current_user.id)
    )
    if shop_id is not None:
        base = base.where(DealProject.shop_id == shop_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(DealProject.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return DealProjectListResponse(items=list(rows), total=total, page=page, size=page_size)


@router.get("/deal-projects/{project_id}", response_model=DealProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_project(project_id, current_user, db)


@router.patch("/deal-projects/{project_id}", response_model=DealProjectResponse)
async def update_project(
    project_id: str,
    body: DealProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    return project


@router.delete("/deal-projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    await db.delete(project)
    return {"ok": True}


# ============================================================
# 菜品清单
# ============================================================


@router.post("/deal-projects/{project_id}/items", response_model=DealItemOut)
async def create_item(
    project_id: str,
    body: DealItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    item = DealItem(project_id=project.id, **body.model_dump())
    db.add(item)
    await db.flush()
    return item


@router.get("/deal-projects/{project_id}/items", response_model=DealItemListResponse)
async def list_items(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    total = (
        await db.execute(
            select(func.count()).select_from(DealItem).where(DealItem.project_id == project.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(DealItem)
            .where(DealItem.project_id == project.id)
            .order_by(DealItem.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return DealItemListResponse(items=list(rows), total=total, page=page, size=page_size)


@router.patch("/deal-projects/{project_id}/items/{item_id}", response_model=DealItemOut)
async def update_item(
    project_id: str,
    item_id: str,
    body: DealItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    item = await _get_item(project, item_id, db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    return item


@router.delete("/deal-projects/{project_id}/items/{item_id}")
async def delete_item(
    project_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    item = await _get_item(project, item_id, db)
    await db.delete(item)
    return {"ok": True}


# ============================================================
# 竞品套餐
# ============================================================


@router.post("/deal-projects/{project_id}/competitor-deals", response_model=CompetitorDealOut)
async def create_competitor(
    project_id: str,
    body: CompetitorDealCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    row = CompetitorDeal(project_id=project.id, **body.model_dump())
    db.add(row)
    await db.flush()
    return row


@router.get(
    "/deal-projects/{project_id}/competitor-deals",
    response_model=CompetitorDealListResponse,
)
async def list_competitors(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    total = (
        await db.execute(
            select(func.count())
            .select_from(CompetitorDeal)
            .where(CompetitorDeal.project_id == project.id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(CompetitorDeal)
            .where(CompetitorDeal.project_id == project.id)
            .order_by(CompetitorDeal.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return CompetitorDealListResponse(items=list(rows), total=total, page=page, size=page_size)


@router.patch(
    "/deal-projects/{project_id}/competitor-deals/{competitor_id}",
    response_model=CompetitorDealOut,
)
async def update_competitor(
    project_id: str,
    competitor_id: str,
    body: CompetitorDealUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    row = await _get_competitor(project, competitor_id, db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    return row


@router.delete("/deal-projects/{project_id}/competitor-deals/{competitor_id}")
async def delete_competitor(
    project_id: str,
    competitor_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    row = await _get_competitor(project, competitor_id, db)
    await db.delete(row)
    return {"ok": True}


# ============================================================
# 套餐方案：生成 / 列表 / 编辑 / 删除
# ============================================================


@router.post(
    "/deal-projects/{project_id}/schemes/generate",
    response_model=SchemeGenerateResponse,
)
async def generate_schemes(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    rate_key = f"deals:generate:{current_user.id}:{project.shop_id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后再试")

    items = (
        await db.execute(
            select(DealItem)
            .where(DealItem.project_id == project.id)
            .order_by(DealItem.created_at)
        )
    ).scalars().all()
    competitors = (
        await db.execute(
            select(CompetitorDeal)
            .where(CompetitorDeal.project_id == project.id)
            .order_by(CompetitorDeal.created_at)
        )
    ).scalars().all()
    shop = await db.get(Shop, project.shop_id)

    agent = DealAgent()
    try:
        raw_schemes = await agent.generate_schemes(
            shop_name=shop.name if shop else "",
            category=shop.category if shop else None,
            platform=project.platform,
            price_band=project.price_band,
            items=[
                {
                    "id": str(it.id),
                    "name": it.name,
                    "category": it.category,
                    "cost_price": float(it.cost_price) if it.cost_price is not None else None,
                    "sale_price": float(it.sale_price),
                    "is_signature": it.is_signature,
                    "is_high_margin": it.is_high_margin,
                }
                for it in items
            ],
            competitor_deals=[
                {
                    "name": cd.name,
                    "price": float(cd.price),
                    "items_summary": cd.items_summary,
                    "note": cd.note,
                }
                for cd in competitors
            ],
        )
    except DealAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    items_by_id = {it.id: it for it in items}
    commission = platform_commission_rate(project.platform)
    resolved: list[dict] = []
    for raw in raw_schemes:
        try:
            resolved.append(_resolve_scheme(raw, items_by_id, commission))
        except DealAgentError as exc:
            if "敏感词" in str(exc):
                raise HTTPException(status_code=422, detail=str(exc))
            raise HTTPException(status_code=502, detail=str(exc))

    # regenerate 语义：旧批次全部归档（含 edited），新批次 +1
    current_max = (
        await db.execute(
            select(func.max(DealScheme.generation_batch)).where(
                DealScheme.project_id == project.id
            )
        )
    ).scalar_one()
    batch = (current_max or 0) + 1
    await db.execute(
        update(DealScheme)
        .where(DealScheme.project_id == project.id)
        .values(is_archived=True)
    )

    created: list[DealScheme] = []
    for rs in resolved:
        scheme = DealScheme(
            project_id=project.id,
            scheme_type=rs["scheme_type"],
            generation_batch=batch,
            title=rs["title"],
            description=rs["description"],
            items=rs["items"],
            original_price=rs["original_price"],
            deal_price=rs["deal_price"],
            cost_estimate=rs["cost_estimate"],
            margin_estimate=rs["margin_estimate"],
            status="draft",
            is_archived=False,
        )
        db.add(scheme)
        await db.flush()
        created.append(scheme)
    project.status = "generated"

    # 仅生成成功才计入频控
    await set_rate_limit(rate_key, _RATE_TTL)
    return SchemeGenerateResponse(
        generation_batch=batch,
        schemes=[_scheme_out(s, []) for s in created],
    )


@router.get("/deal-projects/{project_id}/schemes", response_model=list[DealSchemeOut])
async def list_schemes(
    project_id: str,
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    stmt = (
        select(DealScheme)
        .where(DealScheme.project_id == project.id)
        .order_by(DealScheme.generation_batch.desc(), DealScheme.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(DealScheme.is_archived.is_(False))
    schemes = (await db.execute(stmt)).scalars().all()
    copies: dict[uuid.UUID, list[DealSchemeCopy]] = {}
    if schemes:
        rows = (
            await db.execute(
                select(DealSchemeCopy).where(
                    DealSchemeCopy.scheme_id.in_([s.id for s in schemes])
                )
            )
        ).scalars().all()
        for c in rows:
            copies.setdefault(c.scheme_id, []).append(c)
    return [_scheme_out(s, copies.get(s.id, [])) for s in schemes]


@router.put("/deal-projects/{project_id}/schemes/{scheme_id}", response_model=DealSchemeOut)
async def update_scheme(
    project_id: str,
    scheme_id: str,
    body: SchemeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    scheme = await _get_scheme(project, scheme_id, db)
    data = body.model_dump(exclude_unset=True, mode="json")
    if "items" in data and data["items"] is not None:
        data["items"] = [dict(it) for it in data["items"]]
    for field, value in data.items():
        setattr(scheme, field, value)
    scheme.status = "edited"
    copies = await _scheme_copies(db, scheme.id)
    return _scheme_out(scheme, copies)


@router.delete("/deal-projects/{project_id}/schemes/{scheme_id}")
async def delete_scheme(
    project_id: str,
    scheme_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    scheme = await _get_scheme(project, scheme_id, db)
    await db.delete(scheme)
    return {"ok": True}


# ============================================================
# 平台文案 / 导出到视觉设计
# ============================================================


@router.post(
    "/deal-projects/{project_id}/schemes/{scheme_id}/copy",
    response_model=DealCopyOut,
)
async def generate_copy(
    project_id: str,
    scheme_id: str,
    body: DealCopyGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    scheme = await _get_scheme(project, scheme_id, db)
    # 频控按 scheme 维度独立，不与 generate 共用窗口
    rate_key = f"deals:copy:{current_user.id}:{scheme.id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 20 秒后再试")

    shop = await db.get(Shop, project.shop_id)
    agent = DealCopyAgent()
    try:
        data = await agent.generate(
            platform=body.platform,
            shop_name=shop.name if shop else "",
            shop_category=shop.category if shop else None,
            scheme=_scheme_context(scheme),
        )
    except DealCopyAgentError as exc:
        if "敏感词" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="AI 服务繁忙，请稍后再试")
    except openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务暂时不可用: {exc}")

    result = await db.execute(
        select(DealSchemeCopy).where(
            DealSchemeCopy.scheme_id == scheme.id,
            DealSchemeCopy.platform == body.platform,
        )
    )
    copy = result.scalar_one_or_none()
    if copy:
        copy.title = data["title"]
        copy.selling_points = data["selling_points"]
        copy.rules = data["rules"]
        copy.cover_prompt = data["cover_prompt"]
    else:
        copy = DealSchemeCopy(
            scheme_id=scheme.id,
            platform=body.platform,
            **data,
        )
        db.add(copy)
        await db.flush()

    await set_rate_limit(rate_key, _RATE_TTL)
    return copy


@router.get(
    "/deal-projects/{project_id}/schemes/{scheme_id}/copies",
    response_model=list[DealCopyOut],
)
async def list_copies(
    project_id: str,
    scheme_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    scheme = await _get_scheme(project, scheme_id, db)
    return await _scheme_copies(db, scheme.id)


@router.post(
    "/deal-projects/{project_id}/schemes/{scheme_id}/export-to-design",
    response_model=ExportToDesignResponse,
)
async def export_to_design(
    project_id: str,
    scheme_id: str,
    body: ExportToDesignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project(project_id, current_user, db)
    scheme = await _get_scheme(project, scheme_id, db)
    result = await db.execute(
        select(DealSchemeCopy).where(
            DealSchemeCopy.scheme_id == scheme.id,
            DealSchemeCopy.platform == body.platform,
        )
    )
    copy = result.scalar_one_or_none()
    if copy is None:
        raise HTTPException(
            status_code=400,
            detail=f"该平台（{body.platform}）尚未生成文案，请先生成",
        )
    if not copy.cover_prompt:
        raise HTTPException(status_code=400, detail="该平台文案缺少封面提示词")
    if contains_blocked(copy.cover_prompt):
        raise HTTPException(status_code=422, detail="封面提示词包含敏感词")

    design_project = DesignProject(
        shop_id=project.shop_id,
        title=f"团购工坊导出 · {scheme.title}",
        status="active",
    )
    db.add(design_project)
    await db.flush()
    asset = DesignAsset(
        project_id=design_project.id,
        asset_type="photo",
        source="deals",
        status="active",
        beauty_config={"cover_prompt": copy.cover_prompt},
        dish_name=f"{project.title} · {scheme.title}",
        tagline=copy.title,
    )
    db.add(asset)
    await db.flush()
    return ExportToDesignResponse(
        design_project_id=design_project.id,
        asset_ids=[asset.id],
    )

