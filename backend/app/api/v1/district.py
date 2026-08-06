"""商圈分析 API — analyze / 快照列表 / 详情 / 竞品 / map-config / securityConfig 代理。

流程遵循 SPEC-DISTRICT v0.5：
- 两段式：Step A 无事务调用高德，Step B 单事务落库
- 频控：输入校验 400 不种 token；通过校验后种 60s token
- 失败留痕：纯输入校验/地理编码失败不建记录；周边搜索中途失败建 failed 快照
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import peek_rate_limit, set_rate_limit
from app.models.district_poi import DistrictPoi
from app.models.district_poi_override import DistrictPoiOverride
from app.models.district_snapshot import DistrictSnapshot
from app.models.merchant import Merchant
from app.models.shop import Shop
from app.models.user import User
from app.schemas.district import (
    AnalyzeResponse,
    CompetitorOut,
    MapConfigResponse,
    PoisListResponse,
    PoiOut,
    PoiOverrideListResponse,
    PoiOverrideOut,
    PoiOverrideUpsert,
    SnapshotDetailResponse,
    SnapshotListResponse,
    SnapshotSummaryResponse,
)
from app.services.amap_web import AmapWebError, forward_amap_service, geocode, place_around, place_detail
from app.services.district import compute_stats, map_competitor_types, merge_competitor_detail, parse_poi

logger = logging.getLogger(__name__)

router = APIRouter(tags=["district"])

_RATE_TTL = 60
_DEFAULT_RADIUS = 3000


async def _verify_shop_owner(
    shop_id: str, user: User, db: AsyncSession
) -> Shop:
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


async def _get_snapshot_for_shop(
    snapshot_id: str, shop_id: str, user: User, db: AsyncSession
) -> DistrictSnapshot:
    shop = await _verify_shop_owner(shop_id, user, db)
    try:
        snapshot_uuid = uuid.UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    result = await db.execute(
        select(DistrictSnapshot).where(
            DistrictSnapshot.id == snapshot_uuid,
            DistrictSnapshot.shop_id == shop.id,
        )
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


def _snapshot_summary(snapshot: DistrictSnapshot, excluded_count: int) -> SnapshotSummaryResponse:
    return SnapshotSummaryResponse(
        id=snapshot.id,
        shop_id=snapshot.shop_id,
        center_lng=float(snapshot.center_lng) if snapshot.center_lng is not None else None,
        center_lat=float(snapshot.center_lat) if snapshot.center_lat is not None else None,
        geocode_level=snapshot.geocode_level,
        radius_m=snapshot.radius_m,
        poi_total=snapshot.poi_total,
        competitor_count=snapshot.competitor_count,
        category_stats=snapshot.category_stats,
        density_per_km2=float(snapshot.density_per_km2) if snapshot.density_per_km2 is not None else None,
        mapping_status=snapshot.mapping_status,
        status=snapshot.status,
        error_message=snapshot.error_message,
        excluded_self_count=excluded_count,
        created_at=snapshot.created_at,
    )


# ============================================================
# POST analyze
# ============================================================

@router.post(
    "/shops/{shop_id}/district/analyze",
    response_model=AnalyzeResponse,
)
async def analyze_district(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = await _verify_shop_owner(shop_id, current_user, db)

    # 1. 输入校验：不种频控 token，可立即重试
    if not shop.address or not shop.address.strip():
        raise HTTPException(status_code=400, detail="门店地址为空，请先补充门店地址")

    # 2. 检查并种下 60s 频控 token（通过校验、即将发起地理编码）
    rate_key = f"rate_limit:district_analyze:{current_user.id}:{shop_id}"
    if not await peek_rate_limit(rate_key):
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后重试")
    await set_rate_limit(rate_key, _RATE_TTL)

    # 3. Step A：高德调用（无 DB 事务）
    try:
        geo = await geocode(shop.address)
        raw_pois = await place_around(geo["lng"], geo["lat"], radius=_DEFAULT_RADIUS)
    except AmapWebError as exc:
        if exc.status_code == 429:
            raise HTTPException(status_code=429, detail=exc.detail)
        if exc.status_code == 400:
            # 地理编码输入类失败：不建记录
            raise HTTPException(status_code=400, detail=exc.detail)
        # 502：周边搜索中途失败（已发起搜索）→ 建 failed 快照留痕
        failed = DistrictSnapshot(
            shop_id=shop.id,
            radius_m=_DEFAULT_RADIUS,
            status="failed",
            error_message=exc.detail,
        )
        db.add(failed)
        await db.commit()
        raise HTTPException(status_code=502, detail=exc.detail)

    # 4. 清洗 + 统计
    mapping_full, competitor_mapping = map_competitor_types(shop.category)
    parsed: list[dict] = []
    seen_poi_ids: set[str] = set()
    for poi in raw_pois:
        item = parse_poi(poi, shop.name, competitor_mapping)
        if not item["poi_id"] or item["poi_id"] in seen_poi_ids:
            continue
        seen_poi_ids.add(item["poi_id"])
        parsed.append(item)

    # 4.1 竞品深度数据：对 is_competitor 的 POI 并发拉 place/detail（评分/人均/营业时间/商圈）
    #     最多 _DETAIL_MAX 家，失败只记日志不阻断分析（高德详情缺失是常态）
    _DETAIL_MAX = 20
    competitors = [p for p in parsed if p["is_competitor"] and not p["excluded_as_self"]]
    details: dict[str, dict] = {}
    async def _fetch_detail(poi_id: str) -> tuple[str, dict | None]:
        try:
            return poi_id, await place_detail(poi_id)
        except AmapWebError:
            return poi_id, None

    if competitors:
        for poi_id, detail in await asyncio.gather(
            *(_fetch_detail(c["poi_id"]) for c in competitors[:_DETAIL_MAX])
        ):
            if detail:
                details[poi_id] = detail
        for p in parsed:
            if p["poi_id"] in details:
                merge_competitor_detail(p, details[p["poi_id"]])
        if len(competitors) > _DETAIL_MAX:
            logger.warning("竞品数 %d 超过详情上限 %d，超出的未拉取详情", len(competitors), _DETAIL_MAX)

    # 4.2 人工标记（竞品/非竞品覆盖）优先于自动判定
    if parsed:
        override_rows = (
            await db.execute(
                select(DistrictPoiOverride).where(
                    DistrictPoiOverride.shop_id == shop.id,
                    DistrictPoiOverride.poi_id.in_([p["poi_id"] for p in parsed]),
                )
            )
        ).scalars().all()
        override_by_poi = {o.poi_id: o for o in override_rows}
        for p in parsed:
            ov = override_by_poi.get(p["poi_id"])
            if ov:
                p["is_competitor"] = ov.is_competitor
                p["is_competitor_manual"] = True

    stats = compute_stats(parsed, _DEFAULT_RADIUS)

    # 5. Step B：单事务落库
    snapshot = DistrictSnapshot(
        shop_id=shop.id,
        center_lng=geo["lng"],
        center_lat=geo["lat"],
        geocode_level=geo["level"],
        radius_m=_DEFAULT_RADIUS,
        poi_total=stats["poi_total"],
        competitor_count=stats["competitor_count"],
        category_stats=stats["category_stats"],
        density_per_km2=stats["density_per_km2"],
        mapping_status="full" if mapping_full else "none",
        status="analyzed",
    )
    db.add(snapshot)
    await db.flush()
    db.add_all(
        DistrictPoi(snapshot_id=snapshot.id, **p) for p in parsed
    )
    await db.commit()

    return AnalyzeResponse(
        snapshot_id=snapshot.id,
        poi_total=stats["poi_total"],
        competitor_count=stats["competitor_count"],
        density_per_km2=stats["density_per_km2"],
        mapping_status=snapshot.mapping_status,
        excluded_self_count=stats["excluded_self_count"],
    )


# ============================================================
# GET latest / snapshots
# ============================================================

@router.get("/shops/{shop_id}/district/latest", response_model=SnapshotSummaryResponse)
async def get_latest_snapshot(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)
    result = await db.execute(
        select(DistrictSnapshot)
        .where(DistrictSnapshot.shop_id == shop_id)
        .order_by(DistrictSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="暂无商圈快照，请先执行分析")
    excluded_count = await _count_excluded(snapshot.id, db)
    return _snapshot_summary(snapshot, excluded_count)


@router.get("/shops/{shop_id}/district/snapshots", response_model=SnapshotListResponse)
async def list_snapshots(
    shop_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(analyzed|failed)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_shop_owner(shop_id, current_user, db)
    query = select(DistrictSnapshot).where(DistrictSnapshot.shop_id == shop_id)
    count_query = select(func.count(DistrictSnapshot.id)).where(
        DistrictSnapshot.shop_id == shop_id
    )
    if status:
        query = query.where(DistrictSnapshot.status == status)
        count_query = count_query.where(DistrictSnapshot.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(DistrictSnapshot.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    snapshots = result.scalars().all()
    items = []
    for snap in snapshots:
        excluded_count = await _count_excluded(snap.id, db)
        items.append(_snapshot_summary(snap, excluded_count))
    return SnapshotListResponse(items=items, total=total, page=page, size=size)


async def _count_excluded(snapshot_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(DistrictPoi.id)).where(
            DistrictPoi.snapshot_id == snapshot_id,
            DistrictPoi.excluded_as_self.is_(True),
        )
    )
    return result.scalar() or 0


# ============================================================
# GET snapshot 详情 / POI / competitors
# ============================================================

@router.get(
    "/shops/{shop_id}/district/snapshots/{snapshot_id}",
    response_model=SnapshotDetailResponse,
)
async def get_snapshot_detail(
    shop_id: str,
    snapshot_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    include_excluded: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snapshot = await _get_snapshot_for_shop(snapshot_id, shop_id, current_user, db)
    poi_query = select(DistrictPoi).where(DistrictPoi.snapshot_id == snapshot.id)
    if not include_excluded:
        poi_query = poi_query.where(DistrictPoi.excluded_as_self.is_(False))
    result = await db.execute(
        poi_query.order_by(DistrictPoi.distance_m).offset((page - 1) * size).limit(size)
    )
    pois = [PoiOut.model_validate(p) for p in result.scalars().all()]
    excluded_count = await _count_excluded(snapshot.id, db)
    summary = _snapshot_summary(snapshot, excluded_count)
    return SnapshotDetailResponse(**summary.model_dump(), pois=pois)


@router.get(
    "/shops/{shop_id}/district/snapshots/{snapshot_id}/pois",
    response_model=PoisListResponse,
)
async def list_snapshot_pois(
    shop_id: str,
    snapshot_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    include_excluded: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snapshot = await _get_snapshot_for_shop(snapshot_id, shop_id, current_user, db)
    base = select(DistrictPoi).where(DistrictPoi.snapshot_id == snapshot.id)
    count_base = select(func.count(DistrictPoi.id)).where(
        DistrictPoi.snapshot_id == snapshot.id
    )
    if not include_excluded:
        base = base.where(DistrictPoi.excluded_as_self.is_(False))
        count_base = count_base.where(DistrictPoi.excluded_as_self.is_(False))
    total = (await db.execute(count_base)).scalar() or 0
    result = await db.execute(
        base.order_by(DistrictPoi.distance_m).offset((page - 1) * size).limit(size)
    )
    items = [PoiOut.model_validate(p) for p in result.scalars().all()]
    return PoisListResponse(items=items, total=total, page=page, size=size)


@router.get(
    "/shops/{shop_id}/district/snapshots/{snapshot_id}/competitors",
    response_model=list[CompetitorOut],
)
async def list_competitors(
    shop_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snapshot = await _get_snapshot_for_shop(snapshot_id, shop_id, current_user, db)
    result = await db.execute(
        select(DistrictPoi)
        .where(
            DistrictPoi.snapshot_id == snapshot.id,
            DistrictPoi.is_competitor.is_(True),
        )
        .order_by(DistrictPoi.distance_m)
    )
    return [
        CompetitorOut(
            poi_id=p.poi_id,
            name=p.name,
            category=p.category,
            typecode=p.typecode,
            address=p.address,
            tel=p.tel,
            tag=p.tag,
            business_area=p.business_area,
            rating=float(p.rating) if p.rating is not None else None,
            cost=float(p.cost) if p.cost is not None else None,
            business_hours=p.business_hours,
            distance_m=p.distance_m,
            lng=float(p.lng) if p.lng is not None else None,
            lat=float(p.lat) if p.lat is not None else None,
            is_competitor_manual=p.is_competitor_manual,
        )
        for p in result.scalars().all()
    ]


# ============================================================
# 人工标记（竞品/非竞品覆盖）
# ============================================================

async def _shop_snapshot_ids(shop_id, db):
    """该门店全部快照 id（用于把人工标记物化到快照 POI 行）。"""
    return (
        await db.execute(
            select(DistrictSnapshot.id).where(DistrictSnapshot.shop_id == shop_id)
        )
    ).scalars().all()


@router.get(
    "/shops/{shop_id}/district/poi-overrides",
    response_model=PoiOverrideListResponse,
)
async def list_poi_overrides(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出该门店全部人工标记（含历史 poi，便于管理与导出）。"""
    await _verify_shop_owner(shop_id, current_user, db)
    rows = (
        await db.execute(
            select(DistrictPoiOverride)
            .where(DistrictPoiOverride.shop_id == shop_id)
            .order_by(DistrictPoiOverride.updated_at.desc())
        )
    ).scalars().all()
    return PoiOverrideListResponse(
        items=[PoiOverrideOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.put(
    "/shops/{shop_id}/district/poi-overrides/{poi_id}",
    response_model=PoiOverrideOut,
)
async def upsert_poi_override(
    shop_id: str,
    poi_id: str,
    body: PoiOverrideUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """人工标记：设为竞品或非竞品（幂等，跨快照生效，重新分析后仍沿用）。"""
    shop = await _verify_shop_owner(shop_id, current_user, db)

    poi_name = body.poi_name
    if not poi_name:
        latest = (
            await db.execute(
                select(DistrictSnapshot)
                .where(
                    DistrictSnapshot.shop_id == shop.id,
                    DistrictSnapshot.status == "analyzed",
                )
                .order_by(DistrictSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest:
            poi_name = (
                await db.execute(
                    select(DistrictPoi.name)
                    .where(
                        DistrictPoi.snapshot_id == latest.id,
                        DistrictPoi.poi_id == poi_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()

    override = (
        await db.execute(
            select(DistrictPoiOverride).where(
                DistrictPoiOverride.shop_id == shop.id,
                DistrictPoiOverride.poi_id == poi_id,
            )
        )
    ).scalar_one_or_none()
    if override:
        override.is_competitor = body.is_competitor
        override.note = body.note
        if poi_name:
            override.poi_name = poi_name
    else:
        override = DistrictPoiOverride(
            shop_id=shop.id,
            poi_id=poi_id,
            poi_name=poi_name,
            is_competitor=body.is_competitor,
            note=body.note,
        )
        db.add(override)
    await db.flush()

    snapshot_ids = await _shop_snapshot_ids(shop.id, db)
    if snapshot_ids:
        await db.execute(
            update(DistrictPoi)
            .where(
                DistrictPoi.poi_id == poi_id,
                DistrictPoi.snapshot_id.in_(snapshot_ids),
            )
            .values(is_competitor=body.is_competitor, is_competitor_manual=True)
        )
    await db.commit()
    return PoiOverrideOut.model_validate(override)


@router.delete(
    "/shops/{shop_id}/district/poi-overrides/{poi_id}",
    status_code=204,
)
async def delete_poi_override(
    shop_id: str,
    poi_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消人工标记：删除覆盖，快照 POI 还原为自动判定。"""
    shop = await _verify_shop_owner(shop_id, current_user, db)
    override = (
        await db.execute(
            select(DistrictPoiOverride).where(
                DistrictPoiOverride.shop_id == shop.id,
                DistrictPoiOverride.poi_id == poi_id,
            )
        )
    ).scalar_one_or_none()
    if override:
        await db.delete(override)
    snapshot_ids = await _shop_snapshot_ids(shop.id, db)
    if snapshot_ids:
        await db.execute(
            update(DistrictPoi)
            .where(
                DistrictPoi.poi_id == poi_id,
                DistrictPoi.snapshot_id.in_(snapshot_ids),
                DistrictPoi.is_competitor_manual.is_(True),
            )
            .values(
                is_competitor=DistrictPoi.is_competitor_auto,
                is_competitor_manual=False,
            )
        )
    await db.commit()


# ============================================================
# map-config（全局） + securityConfig 代理
# ============================================================

@router.get("/district/map-config", response_model=MapConfigResponse)
async def get_map_config(
    _user: User = Depends(get_current_user),
):
    from app.core.config import settings

    if not settings.AMAP_JS_KEY:
        raise HTTPException(status_code=503, detail="高德 JS Key 未配置")
    return MapConfigResponse(amap_js_key=settings.AMAP_JS_KEY)


@router.get("/district/_AMapService/{path:path}")
async def amap_service_proxy(path: str, request: Request):
    """高德 JS API 服务代理（无需 JWT，地图初始化请求不带 token）。

    按官方模式把 SDK 请求按路径转发到高德对应服务，并附加 securityJsCode。
    """
    params = {k: v for k, v in request.query_params.items()}
    try:
        resp = await forward_amap_service(path, params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"高德服务代理失败: {exc}")
    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "application/json"),
        status_code=resp.status_code,
    )
