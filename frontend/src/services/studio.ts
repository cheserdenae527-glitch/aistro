import api from "./api";

export type StudioProjectStatus = "draft" | "generated";
export type DeckTemplate = "editorial" | "swiss";
export type DeckStatus = "draft" | "rendered" | "failed";

export interface StudioProject {
  id: string;
  shop_id: string;
  title: string;
  status: StudioProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface CopyTitleItem {
  text: string;
  strategy: string;
}

export interface ImageGuidePage {
  position: string;
  purpose: string;
  prompt: string;
}

export interface CopyImageGuide {
  cover_prompt: string;
  pages: ImageGuidePage[];
}

export interface StudioCopy {
  id: string;
  project_id: string;
  input_payload: Record<string, string> | null;
  titles: CopyTitleItem[] | null;
  body: string | null;
  tags: string[] | null;
  image_guide: CopyImageGuide | null;
  created_at: string;
}

export interface PageSpec {
  title: string;
  bullets: string[];
  image_index: number | null;
}

export interface DeckImage {
  page: number;
  url: string;
  width: number;
  height: number;
}

export interface SourceAsset {
  source: "design" | "upload";
  asset_id?: string | null;
  url?: string | null;
}

export interface QaPage {
  page: number;
  pass: boolean;
  checks: {
    density: { pass: boolean; coverage: number; bands: number[]; issues: string[] };
    overflow: { pass: boolean; overflow_px: number };
    bottom_blank: { pass: boolean; bottom_gap_px: number };
  };
  issues: string[];
}

export interface QaReport {
  all_pass: boolean;
  pages: QaPage[];
}

export interface StudioDeck {
  id: string;
  project_id: string;
  copy_id: string;
  template: DeckTemplate;
  theme: string;
  page_count: number;
  page_specs: PageSpec[] | null;
  source_assets: SourceAsset[] | null;
  images: DeckImage[] | null;
  qa_report: QaReport | null;
  status: DeckStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface StudioProjectDetail extends StudioProject {
  copies: StudioCopy[];
  decks: StudioDeck[];
}

export interface CopyGenerateRequest {
  category: string;
  style: string;
  price_range: string;
  topic: string;
  shop_name: string;
}

export interface DeckCreateRequest {
  copy_id: string;
  template: DeckTemplate;
  theme: string;
  page_count: number;
  asset_ids: string[];
}

export interface DeckCreateResponse {
  deck_id: string;
  images: DeckImage[];
  qa_report: QaReport | null;
  status: DeckStatus;
  error_message: string | null;
}

export interface ExportToDesignResponse {
  design_project_id: string;
  asset_ids: string[];
}

export const studioService = {
  // ---- projects ----
  listProjects: (shopId?: string) =>
    api.get<StudioProject[]>("/studio/projects", { params: { shop_id: shopId } }),

  createProject: (data: { shop_id: string; title: string }) =>
    api.post<StudioProject>("/studio/projects", data),

  getProject: (id: string) => api.get<StudioProjectDetail>(`/studio/projects/${id}`),

  updateProject: (id: string, data: { title?: string; status?: StudioProjectStatus }) =>
    api.patch<StudioProject>(`/studio/projects/${id}`, data),

  deleteProject: (id: string) => api.delete<{ ok: boolean }>(`/studio/projects/${id}`),

  // ---- copies ----
  generateCopy: (projectId: string, data: CopyGenerateRequest) =>
    api.post<StudioCopy>(`/studio/projects/${projectId}/copy/generate`, data, {
      timeout: 60_000,
    }),

  updateCopy: (copyId: string, data: { titles?: CopyTitleItem[]; body?: string; tags?: string[]; image_guide?: CopyImageGuide }) =>
    api.patch<StudioCopy>(`/studio/copies/${copyId}`, data),

  enrichImagePrompt: (copyId: string, direction: string) =>
    api.post<{ main_idea: string; prompt: string }>(
      `/studio/copies/${copyId}/image-prompt/enrich`,
      { direction },
      { timeout: 60_000 }
    ),

  // ---- decks ----
  createDeck: (projectId: string, body: DeckCreateRequest) =>
    api.post<DeckCreateResponse>(`/studio/projects/${projectId}/decks`, body, {
      timeout: 180_000,
    }),

  createDeckWithFiles: (
    projectId: string,
    params: {
      copy_id: string;
      template: DeckTemplate;
      theme: string;
      page_count: number;
      asset_ids: string[];
      files: File[];
    }
  ) => {
    const fd = new FormData();
    fd.append("copy_id", params.copy_id);
    fd.append("template", params.template);
    fd.append("theme", params.theme);
    fd.append("page_count", String(params.page_count));
    if (params.asset_ids.length > 0) {
      fd.append("asset_ids", JSON.stringify(params.asset_ids));
    }
    params.files.forEach((f) => fd.append("files", f));
    return api.post<DeckCreateResponse>(`/studio/projects/${projectId}/decks`, fd, {
      timeout: 180_000,
    });
  },

  getDeck: (deckId: string) => api.get<StudioDeck>(`/studio/decks/${deckId}`),

  exportToDesign: (deckId: string) =>
    api.post<ExportToDesignResponse>(`/studio/decks/${deckId}/export-to-design`),
};
