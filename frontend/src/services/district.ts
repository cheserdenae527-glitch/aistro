// 商圈分析 API 服务 — 对应 docs/contracts/district-api.md v1.0
import api from "./api";

export interface CategoryStat {
  category: string;
  count: number;
}

export type MappingStatus = "full" | "none";
export type SnapshotStatus = "analyzed" | "failed";

export interface SnapshotSummary {
  id: string;
  shop_id: string;
  center_lng: number | null;
  center_lat: number | null;
  geocode_level: string | null;
  radius_m: number;
  poi_total: number;
  competitor_count: number;
  category_stats: CategoryStat[] | null;
  density_per_km2: number | null;
  mapping_status: MappingStatus;
  status: SnapshotStatus;
  error_message: string | null;
  excluded_self_count: number;
  created_at: string;
}

export interface SnapshotListResponse {
  items: SnapshotSummary[];
  total: number;
  page: number;
  size: number;
}

export interface Poi {
  id: string;
  poi_id: string;
  name: string;
  category: string | null;
  typecode: string | null;
  address: string | null;
  tel: string | null;
  tag: string | null;
  business_area: string | null;
  rating: number | null;
  cost: number | null;
  business_hours: string | null;
  lng: number | null;
  lat: number | null;
  distance_m: number;
  is_competitor: boolean;
  is_competitor_auto?: boolean;
  is_competitor_manual?: boolean;
  excluded_as_self: boolean;
}

export interface PoisListResponse {
  items: Poi[];
  total: number;
  page: number;
  size: number;
}

export interface Competitor {
  poi_id: string;
  name: string;
  category: string | null;
  typecode: string | null;
  address: string | null;
  tel: string | null;
  tag: string | null;
  business_area: string | null;
  rating: number | null;
  cost: number | null;
  business_hours: string | null;
  distance_m: number;
  lng: number | null;
  lat: number | null;
  is_competitor_manual?: boolean;
}

export interface PoiOverrideUpsert {
  is_competitor: boolean;
  note?: string | null;
  poi_name?: string | null;
}

export interface PoiOverride {
  poi_id: string;
  poi_name: string | null;
  is_competitor: boolean;
  note: string | null;
  updated_at: string;
}

export interface PoiOverrideListResponse {
  items: PoiOverride[];
  total: number;
}

export interface AnalyzeResponse {
  snapshot_id: string;
  poi_total: number;
  competitor_count: number;
  density_per_km2: number | null;
  mapping_status: MappingStatus;
  excluded_self_count: number;
}

export interface MapConfig {
  amap_js_key: string;
  proxy_path: string;
}

export interface SnapshotDetail extends SnapshotSummary {
  pois: Poi[];
}

export interface SnapshotListParams {
  page?: number;
  size?: number;
  status?: SnapshotStatus;
}

export interface PoiListParams {
  page?: number;
  size?: number;
  include_excluded?: boolean;
}

export const districtService = {
  analyze: (shopId: string) =>
    api.post<AnalyzeResponse>(`/shops/${shopId}/district/analyze`),

  latest: (shopId: string) =>
    api.get<SnapshotSummary>(`/shops/${shopId}/district/latest`),

  listSnapshots: (shopId: string, params?: SnapshotListParams) =>
    api.get<SnapshotListResponse>(`/shops/${shopId}/district/snapshots`, { params }),

  snapshotDetail: (shopId: string, snapshotId: string) =>
    api.get<SnapshotDetail>(`/shops/${shopId}/district/snapshots/${snapshotId}`),

  listPois: (shopId: string, snapshotId: string, params?: PoiListParams) =>
    api.get<PoisListResponse>(`/shops/${shopId}/district/snapshots/${snapshotId}/pois`, {
      params,
    }),

  competitors: (shopId: string, snapshotId: string) =>
    api.get<Competitor[]>(`/shops/${shopId}/district/snapshots/${snapshotId}/competitors`),

  listOverrides: (shopId: string) =>
    api.get<PoiOverrideListResponse>(`/shops/${shopId}/district/poi-overrides`),

  setPoiOverride: (shopId: string, poiId: string, body: PoiOverrideUpsert) =>
    api.put<PoiOverride>(`/shops/${shopId}/district/poi-overrides/${poiId}`, body),

  deletePoiOverride: (shopId: string, poiId: string) =>
    api.delete(`/shops/${shopId}/district/poi-overrides/${poiId}`),

  mapConfig: () => api.get<MapConfig>("/district/map-config"),
};
