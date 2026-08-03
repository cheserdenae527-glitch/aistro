import api from "./api";

export type DesignProjectStatus = "draft" | "active" | "archived";
export type DesignAssetType = "dish" | "logo" | "photo";
export type DesignAssetStatus = "pending" | "active" | "discarded";
export type FilterPreset = "none" | "warm" | "japanese" | "vivid" | "bw";
export type MenuType = "xhs" | "a4";

export interface DesignProject {
  id: string;
  shop_id: string;
  title: string;
  status: DesignProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface DesignAsset {
  id: string;
  project_id: string;
  asset_type: DesignAssetType;
  source: "upload" | "ai";
  status: DesignAssetStatus;
  batch_id: string | null;
  derived_from_asset_id: string | null;
  original_url: string | null;
  processed_url: string | null;
  thumb_url: string | null;
  edit_stack: unknown[] | null;
  beauty_config: Record<string, unknown> | null;
  dish_name: string | null;
  price: string | null;
  tagline: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssetCandidate {
  aid: string;
  url: string;
  thumb_url: string | null;
  batch_id: string;
}

export interface GenerateCandidatesResponse {
  batch_id: string;
  candidates: AssetCandidate[];
}

export interface ConfirmResponse {
  batch_id: string;
  active_aid: string;
  discarded_aids: string[];
}

export interface MenuColorScheme {
  primary: string;
  secondary: string;
  accent: string;
  text: string;
  preset_name?: string | null;
}

export interface MenuItemInput {
  asset_id: string;
  section?: string;
  sort?: number;
  override_name?: string | null;
  override_price?: string | null;
  override_tagline?: string | null;
}

export interface MenuDesign {
  id: string;
  project_id: string;
  menu_type: MenuType;
  template_id: string;
  shop_name: string | null;
  logo_url: string | null;
  color_scheme: MenuColorScheme | null;
  items: MenuItemInput[] | null;
  output_url: string | null;
  status: "draft" | "rendered";
  version: number;
  created_at: string;
  updated_at: string;
}

export const designService = {
  // ---- projects ----
  listProjects: (shopId: string, status?: DesignProjectStatus) =>
    api.get<DesignProject[]>("/design-projects", {
      params: { shop_id: shopId, status },
    }),

  createProject: (data: { shop_id: string; title: string; status?: DesignProjectStatus }) =>
    api.post<DesignProject>("/design-projects", data),

  getProject: (projectId: string) =>
    api.get<DesignProject>(`/design-projects/${projectId}`),

  updateProject: (projectId: string, data: { title?: string; status?: DesignProjectStatus }) =>
    api.patch<DesignProject>(`/design-projects/${projectId}`, data),

  deleteProject: (projectId: string) =>
    api.delete<{ ok: boolean }>(`/design-projects/${projectId}`),

  // ---- assets ----
  listAssets: (projectId: string, params?: { status?: DesignAssetStatus; asset_type?: DesignAssetType; include_derived?: boolean }) =>
    api.get<DesignAsset[]>(`/design-projects/${projectId}/assets`, { params }),

  uploadAsset: (
    projectId: string,
    file: File,
    meta: { asset_type?: DesignAssetType; dish_name?: string; price?: string; tagline?: string }
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("asset_type", meta.asset_type || "photo");
    if (meta.dish_name) fd.append("dish_name", meta.dish_name);
    if (meta.price) fd.append("price", meta.price);
    if (meta.tagline) fd.append("tagline", meta.tagline);
    return api.post<DesignAsset>(`/design-projects/${projectId}/assets`, fd);
  },

  updateAsset: (
    projectId: string,
    assetId: string,
    data: { asset_type?: DesignAssetType; dish_name?: string | null; price?: string | null; tagline?: string | null }
  ) =>
    api.patch<DesignAsset>(`/design-projects/${projectId}/assets/${assetId}`, data),

  deleteAsset: (projectId: string, assetId: string) =>
    api.delete<{ ok: boolean }>(`/design-projects/${projectId}/assets/${assetId}`),

  generateAssets: (projectId: string, prompt: string, refFile?: File | null, assetType?: DesignAssetType) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    if (refFile) fd.append("ref_image", refFile);
    if (assetType) fd.append("asset_type", assetType);
    return api.post<GenerateCandidatesResponse>(
      `/design-projects/${projectId}/assets/generate`,
      fd,
      { timeout: 180000 }
    );
  },

  confirmAsset: (projectId: string, assetId: string) =>
    api.post<ConfirmResponse>(`/design-projects/${projectId}/assets/${assetId}/confirm`),

  beautifyAsset: (
    projectId: string,
    assetId: string,
    data: { mode?: "enhance" | "color_correct"; brightness?: number; contrast?: number; saturation?: number }
  ) =>
    api.post<DesignAsset>(`/design-projects/${projectId}/assets/${assetId}/beautify`, data, {
      timeout: 60000,
    }),

  bgReplace: (projectId: string, assetId: string, prompt: string) =>
    api.post<GenerateCandidatesResponse>(
      `/design-projects/${projectId}/assets/${assetId}/bg-replace`,
      { prompt },
      { timeout: 180000 }
    ),

  enhance: (projectId: string, assetId: string, prompt: string) =>
    api.post<GenerateCandidatesResponse>(
      `/design-projects/${projectId}/assets/${assetId}/enhance`,
      { prompt },
      { timeout: 180000 }
    ),

  aiBeautify: (projectId: string, assetId: string, prompt?: string) =>
    api.post<GenerateCandidatesResponse>(
      `/design-projects/${projectId}/assets/${assetId}/ai-beautify`,
      { prompt: prompt || null },
      { timeout: 180000 }
    ),

  generateBeautifyPrompt: (projectId: string, assetId: string, focus?: string, dishName?: string | null) =>
    api.post<{ prompt: string }>(
      `/design-projects/${projectId}/assets/${assetId}/ai-beautify/prompt`,
      { focus: focus || null, dish_name: dishName || null }
    ),

  saveAsset: (
    projectId: string,
    assetId: string,
    imageBase64: string,
    editStack?: unknown[] | null,
    beautyConfig?: Record<string, unknown> | null
  ) =>
    api.post<DesignAsset>(`/design-projects/${projectId}/assets/${assetId}/save`, {
      image_base64: imageBase64,
      edit_stack: editStack,
      beauty_config: beautyConfig,
    }),

  // ---- menus ----
  listMenus: (projectId: string) =>
    api.get<MenuDesign[]>(`/design-projects/${projectId}/menus`),

  getMenu: (projectId: string, menuId: string) =>
    api.get<MenuDesign>(`/design-projects/${projectId}/menus/${menuId}`),

  createMenu: (projectId: string, data: { menu_type: MenuType; template_id?: string; shop_name?: string | null; logo_url?: string | null; color_scheme?: MenuColorScheme | null; items: MenuItemInput[] }) =>
    api.post<MenuDesign>(`/design-projects/${projectId}/menus`, data),

  updateMenu: (projectId: string, menuId: string, data: { version: number; menu_type?: MenuType; template_id?: string; shop_name?: string | null; logo_url?: string | null; color_scheme?: MenuColorScheme | null; items?: MenuItemInput[] | null }) =>
    api.patch<MenuDesign>(`/design-projects/${projectId}/menus/${menuId}`, data),

  renderMenu: (projectId: string, menuId: string, version: number) =>
    api.post<{ id: string; output_url: string; status: string; version: number }>(
      `/design-projects/${projectId}/menus/${menuId}/render`,
      { version },
      { timeout: 90000 }
    ),
};
