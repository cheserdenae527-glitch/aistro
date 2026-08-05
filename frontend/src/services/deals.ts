import api from "./api";

export type DealPlatform = "douyin" | "meituan" | "xiaohongshu";
export type DealItemCategory = "signature" | "staple" | "snack" | "drink";
export type DealSchemeType = "hook" | "profit" | "scenario";
export type DealSchemeStatus = "draft" | "edited" | "generated";

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface DealProject {
  id: string;
  shop_id: string;
  title: string;
  platform: DealPlatform;
  price_band: string | null;
  status: "draft" | "generated";
  created_at: string;
  updated_at: string;
}

export interface DealItem {
  id: string;
  project_id: string;
  name: string;
  category: DealItemCategory;
  cost_price: string | null;
  sale_price: string;
  is_signature: boolean;
  is_high_margin: boolean;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompetitorDeal {
  id: string;
  project_id: string;
  name: string;
  price: string;
  items_summary: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface SchemeItem {
  item_id: string;
  name: string;
  qty: number;
  sale_price: number;
  cost_price: number;
}

export interface MarginEstimate {
  gross_margin: number;
  platform_commission_rate: number;
  net_margin: number;
  note: string;
}

export interface DealSchemeCopy {
  id: string;
  scheme_id: string;
  platform: DealPlatform;
  title: string;
  selling_points: string[] | null;
  rules: string | null;
  cover_prompt: string | null;
  created_at: string;
  updated_at: string;
}

export interface DealScheme {
  id: string;
  project_id: string;
  scheme_type: DealSchemeType;
  generation_batch: number;
  title: string;
  description: string | null;
  items: SchemeItem[] | null;
  original_price: string;
  deal_price: string;
  cost_estimate: string | null;
  margin_estimate: MarginEstimate | null;
  status: DealSchemeStatus;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  copies: DealSchemeCopy[];
}

export interface SchemeGenerateResponse {
  generation_batch: number;
  schemes: DealScheme[];
}

export interface ExportToDesignResponse {
  design_project_id: string;
  asset_ids: string[];
}

export interface DealProjectCreate {
  shop_id: string;
  title: string;
  platform: DealPlatform;
  price_band?: string;
}

export interface DealItemCreate {
  name: string;
  category: DealItemCategory;
  cost_price?: number | null;
  sale_price: number;
  is_signature?: boolean;
  is_high_margin?: boolean;
  image_url?: string | null;
}

export interface CompetitorDealCreate {
  name: string;
  price: number;
  items_summary: string;
  note?: string | null;
}

export interface SchemeUpdate {
  title?: string;
  description?: string | null;
  items?: SchemeItem[];
  original_price?: number;
  deal_price?: number;
  cost_estimate?: number;
  margin_estimate?: Partial<MarginEstimate> | null;
}

export interface DealCopyUpdate {
  title?: string;
  selling_points?: string[];
  rules?: string | null;
  cover_prompt?: string | null;
}

export const dealService = {
  // ---- 项目 ----
  listProjects: (params?: { shop_id?: string; page?: number; page_size?: number }) =>
    api.get<Paginated<DealProject>>("/deal-projects", { params }),

  createProject: (data: DealProjectCreate) => api.post<DealProject>("/deal-projects", data),

  getProject: (id: string) => api.get<DealProject>(`/deal-projects/${id}`),

  updateProject: (id: string, data: { title?: string; platform?: DealPlatform; price_band?: string | null }) =>
    api.patch<DealProject>(`/deal-projects/${id}`, data),

  deleteProject: (id: string) => api.delete<{ ok: boolean }>(`/deal-projects/${id}`),

  // ---- 菜品 ----
  listItems: (projectId: string, params?: { page?: number; page_size?: number }) =>
    api.get<Paginated<DealItem>>(`/deal-projects/${projectId}/items`, { params }),

  createItem: (projectId: string, data: DealItemCreate) =>
    api.post<DealItem>(`/deal-projects/${projectId}/items`, data),

  updateItem: (projectId: string, itemId: string, data: Partial<DealItemCreate>) =>
    api.patch<DealItem>(`/deal-projects/${projectId}/items/${itemId}`, data),

  deleteItem: (projectId: string, itemId: string) =>
    api.delete<{ ok: boolean }>(`/deal-projects/${projectId}/items/${itemId}`),

  uploadItemImage: (projectId: string, itemId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<DealItem>(`/deal-projects/${projectId}/items/${itemId}/image`, fd, {
      timeout: 60_000,
    });
  },

  // ---- 竞品 ----
  listCompetitors: (projectId: string, params?: { page?: number; page_size?: number }) =>
    api.get<Paginated<CompetitorDeal>>(`/deal-projects/${projectId}/competitor-deals`, { params }),

  createCompetitor: (projectId: string, data: CompetitorDealCreate) =>
    api.post<CompetitorDeal>(`/deal-projects/${projectId}/competitor-deals`, data),

  updateCompetitor: (projectId: string, competitorId: string, data: Partial<CompetitorDealCreate>) =>
    api.patch<CompetitorDeal>(`/deal-projects/${projectId}/competitor-deals/${competitorId}`, data),

  deleteCompetitor: (projectId: string, competitorId: string) =>
    api.delete<{ ok: boolean }>(`/deal-projects/${projectId}/competitor-deals/${competitorId}`),

  // ---- 方案 ----
  generateSchemes: (projectId: string) =>
    api.post<SchemeGenerateResponse>(`/deal-projects/${projectId}/schemes/generate`, {}, { timeout: 120_000 }),

  listSchemes: (projectId: string, includeArchived = false) =>
    api.get<DealScheme[]>(`/deal-projects/${projectId}/schemes`, {
      params: { include_archived: includeArchived },
    }),

  updateScheme: (projectId: string, schemeId: string, data: SchemeUpdate) =>
    api.put<DealScheme>(`/deal-projects/${projectId}/schemes/${schemeId}`, data),

  deleteScheme: (projectId: string, schemeId: string) =>
    api.delete<{ ok: boolean }>(`/deal-projects/${projectId}/schemes/${schemeId}`),

  // ---- 平台文案 ----
  generateCopy: (projectId: string, schemeId: string, platform: DealPlatform) =>
    api.post<DealSchemeCopy>(`/deal-projects/${projectId}/schemes/${schemeId}/copy`, { platform }, { timeout: 60_000 }),

  listCopies: (projectId: string, schemeId: string) =>
    api.get<DealSchemeCopy[]>(`/deal-projects/${projectId}/schemes/${schemeId}/copies`),

  updateCopy: (projectId: string, schemeId: string, copyId: string, data: DealCopyUpdate) =>
    api.patch<DealSchemeCopy>(`/deal-projects/${projectId}/schemes/${schemeId}/copies/${copyId}`, data),

  // ---- 导出 ----
  exportToDesign: (projectId: string, schemeId: string, platform: DealPlatform) =>
    api.post<ExportToDesignResponse>(`/deal-projects/${projectId}/schemes/${schemeId}/export-to-design`, { platform }),
};
