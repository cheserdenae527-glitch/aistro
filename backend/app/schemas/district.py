"""商圈分析 Pydantic Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeResponse(BaseModel):
    snapshot_id: uuid.UUID
    poi_total: int
    competitor_count: int
    density_per_km2: float | None
    mapping_status: str
    excluded_self_count: int


class CategoryStat(BaseModel):
    category: str
    count: int


class PoiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    poi_id: str
    name: str
    category: str | None = None
    address: str | None = None
    lng: float | None = None
    lat: float | None = None
    distance_m: int
    is_competitor: bool
    excluded_as_self: bool


class SnapshotSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    center_lng: float | None = None
    center_lat: float | None = None
    geocode_level: str | None = None
    radius_m: int
    poi_total: int
    competitor_count: int
    category_stats: list[CategoryStat] | None = None
    density_per_km2: float | None = None
    mapping_status: str
    status: str
    error_message: str | None = None
    excluded_self_count: int = 0
    created_at: datetime


class SnapshotListResponse(BaseModel):
    items: list[SnapshotSummaryResponse]
    total: int
    page: int
    size: int


class SnapshotDetailResponse(SnapshotSummaryResponse):
    pois: list[PoiOut]


class PoisListResponse(BaseModel):
    items: list[PoiOut]
    total: int
    page: int
    size: int


class CompetitorOut(BaseModel):
    poi_id: str
    name: str
    category: str | None = None
    address: str | None = None
    distance_m: int
    lng: float | None = None
    lat: float | None = None


class MapConfigResponse(BaseModel):
    amap_js_key: str
    proxy_path: str = "/api/v1/district/_AMapService"
