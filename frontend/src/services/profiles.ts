import api from "./api";

export interface ColorScheme {
  primary: string;
  secondary: string;
  accent: string;
  text: string;
  preset_name: string | null;
}

export interface ColorSchemePreset {
  name: string;
  primary: string;
  secondary: string;
  accent: string;
  text: string;
  description: string | null;
}

export interface AiVariant {
  id: string;
  color_scheme: ColorScheme;
  nickname_options: string[];
  bio: string;
  avatar_prompt: string;
  bg_prompt: string;
  filtered: boolean;
  bio_flagged: boolean;
}

export interface StyleAnalysis {
  vibe?: string | null;
  dominant_colors?: (string | null)[] | null;
  nickname_style?: string | null;
  bio_style?: string | null;
  avatar_style?: string | null;
  bg_style?: string | null;
  suggested_prompt?: string | null;
}

export interface ImageOption {
  object_name: string;
  url: string;
}

export interface ImageGenerateOptionsResponse {
  url: string;
  prompt: string;
  options: ImageOption[];
}

export interface PromptGenerateResponse {
  section: "avatar" | "bg";
  prompt: string;
}

export interface HealthCheckResult {
  first_impression: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  checked_at?: string;
  snapshot?: HealthSnapshot | null;
}

export interface HealthSnapshot {
  nickname: string;
  bio: string;
  avatar_prompt: string;
  bg_prompt: string;
  pinned_notes: PinnedNote[];
  color_primary: string | null;
  color_secondary: string | null;
  color_accent: string | null;
  color_text: string | null;
  has_avatar: boolean;
  has_bg: boolean;
}

export interface ProfileHistoryItem {
  id: string;
  version: number;
  created_at: string;
  nickname: string | null;
  bio: string | null;
  pinned_notes: PinnedNote[] | null;
  color_primary: string | null;
  avatar_set: boolean;
  bg_set: boolean;
}

export interface ImageJobCreateResponse {
  job_id: string;
  status: string;
}

export interface ImageJobResponse {
  id: string;
  section: string;
  status: "pending" | "running" | "success" | "failed";
  options: ImageOption[] | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface PinnedNote {
  title: string;
  content: string;
}

export interface ShopProfile {
  id: string;
  shop_id: string;
  platform: string;
  nickname: string | null;
  bio: string | null;
  avatar_url: string | null;
  avatar_original_url: string | null;
  avatar_gen_prompt: string | null;
  avatar_options?: ImageOption[] | null;
  bg_image_url: string | null;
  bg_original_url: string | null;
  bg_gen_prompt: string | null;
  bg_options?: ImageOption[] | null;
  color_primary: string | null;
  color_secondary: string | null;
  color_accent: string | null;
  color_text: string | null;
  color_mode: string | null;
  color_preset_name: string | null;
  ai_variants: { variants: AiVariant[] } | null;
  health_check?: HealthCheckResult | null;
  pinned_notes?: PinnedNote[] | null;
  bio_flagged: boolean;
  status: string;
  version: number;
}

export const profileService = {
  analyzeStyle: (shopId: string, platform: string, file: File) => {
    const fd = new FormData();
    fd.append("image", file);
    return api.post<StyleAnalysis>(
      `/shops/${shopId}/profiles/${platform}/analyze-style`,
      fd
    );
  },
  get: (shopId: string, platform: string) =>
    api.get<ShopProfile>(`/shops/${shopId}/profiles/${platform}`),

  update: (shopId: string, platform: string, data: Record<string, unknown>) =>
    api.put<ShopProfile>(`/shops/${shopId}/profiles/${platform}`, data),

  generate: (shopId: string, platform: string, data: { category: string; style: string; price_range: string }) =>
    api.post<{ variants: AiVariant[]; generated_at: string }>(
      `/shops/${shopId}/profiles/${platform}/generate`,
      data
    ),

  generatePrompt: (
    shopId: string,
    platform: string,
    data: { section: "avatar" | "bg"; category: string; style: string; price_range: string }
  ) =>
    api.post<PromptGenerateResponse>(
      `/shops/${shopId}/profiles/${platform}/generate-prompt`,
      data
    ),

  healthCheck: (
    shopId: string,
    platform: string,
    data: {
      nickname: string;
      bio: string;
      avatar_prompt: string;
      bg_prompt: string;
      color_primary: string | null;
      color_secondary: string | null;
      color_accent: string | null;
      color_text: string | null;
      pinned_notes: PinnedNote[];
      has_avatar: boolean;
      has_bg: boolean;
    }
  ) =>
    api.post<HealthCheckResult>(
      `/shops/${shopId}/profiles/${platform}/health-check`,
      data
    ),

  generatePinnedNotes: (
    shopId: string,
    platform: string,
    data: { category: string; style: string; price_range: string }
  ) =>
    api.post<{ notes: PinnedNote[] }>(
      `/shops/${shopId}/profiles/${platform}/generate-pinned-notes`,
      data
    ),

  generateProfileOptions: (
    shopId: string,
    platform: string,
    kind: "nickname" | "bio",
    data: { category: string; style: string; price_range: string }
  ) =>
    api.post<{ options: string[] }>(
      `/shops/${shopId}/profiles/${platform}/generate-profile-options`,
      { kind, ...data }
    ),

  rewriteByHealthCheck: (
    shopId: string,
    platform: string,
    data: {
      nickname: string;
      bio: string;
      pinned_notes: PinnedNote[];
      weaknesses: string[];
      suggestions: string[];
      category: string;
      style: string;
      price_range: string;
    }
  ) =>
    api.post<{
      nickname_options: string[];
      bio: string;
      pinned_notes: PinnedNote[];
      bio_flagged: boolean;
    }>(
      `/shops/${shopId}/profiles/${platform}/rewrite-by-health-check`,
      data
    ),

  generateAvatar: (shopId: string, platform: string, prompt: string) =>
    api.post<ImageGenerateOptionsResponse>(
      `/shops/${shopId}/profiles/${platform}/generate-avatar`,
      { prompt },
      { timeout: 180000 }
    ),

  createImageJob: (
    shopId: string,
    platform: string,
    section: "avatar" | "bg",
    prompt: string
  ) => {
    const path = section === "avatar" ? "generate-avatar-job" : "generate-bg-image-job";
    return api.post<ImageJobCreateResponse>(
      `/shops/${shopId}/profiles/${platform}/${path}`,
      { prompt }
    );
  },

  createImageJobWithRef: (
    shopId: string,
    platform: string,
    section: "avatar" | "bg",
    prompt: string,
    refFile?: File | null
  ) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    if (refFile) fd.append("ref_image", refFile);
    const path = section === "avatar"
      ? "generate-avatar-with-ref-job"
      : "generate-bg-image-with-ref-job";
    return api.post<ImageJobCreateResponse>(
      `/shops/${shopId}/profiles/${platform}/${path}`,
      fd
    );
  },

  getImageJob: (shopId: string, platform: string, jobId: string) =>
    api.get<ImageJobResponse>(
      `/shops/${shopId}/profiles/${platform}/image-jobs/${jobId}`
    ),

  getHistory: (shopId: string, platform: string) =>
    api.get<ProfileHistoryItem[]>(`/shops/${shopId}/profiles/${platform}/history`),

  restoreHistory: (shopId: string, platform: string, historyId: string) =>
    api.post<ShopProfile>(
      `/shops/${shopId}/profiles/${platform}/history/${historyId}/restore`
    ),

  generateBgImage: (shopId: string, platform: string, prompt: string) =>
    api.post<ImageGenerateOptionsResponse>(
      `/shops/${shopId}/profiles/${platform}/generate-bg-image`,
      { prompt },
      { timeout: 180000 }
    ),

  generateAvatarWithRef: (
    shopId: string,
    platform: string,
    prompt: string,
    refFile?: File | null
  ) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    if (refFile) fd.append("ref_image", refFile);
    return api.post<ImageGenerateOptionsResponse>(
      `/shops/${shopId}/profiles/${platform}/generate-avatar-with-ref`,
      fd,
      { timeout: 180000 }
    );
  },

  generateBgImageWithRef: (
    shopId: string,
    platform: string,
    prompt: string,
    refFile?: File | null
  ) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    if (refFile) fd.append("ref_image", refFile);
    return api.post<ImageGenerateOptionsResponse>(
      `/shops/${shopId}/profiles/${platform}/generate-bg-image-with-ref`,
      fd,
      { timeout: 180000 }
    );
  },

  selectAvatar: (shopId: string, platform: string, objectName: string) =>
    api.post<{ url: string; prompt: string }>(
      `/shops/${shopId}/profiles/${platform}/select-avatar`,
      { object_name: objectName }
    ),

  selectBgImage: (shopId: string, platform: string, objectName: string) =>
    api.post<{ url: string; prompt: string }>(
      `/shops/${shopId}/profiles/${platform}/select-bg-image`,
      { object_name: objectName }
    ),

  removeGalleryImage: (
    shopId: string,
    platform: string,
    section: "avatar" | "bg",
    objectName: string
  ) =>
    api.post<ImageOption[]>(
      `/shops/${shopId}/profiles/${platform}/remove-gallery-image`,
      { section, object_name: objectName }
    ),

  uploadAvatar: (shopId: string, platform: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<{ url: string; prompt: string }>(
      `/shops/${shopId}/profiles/${platform}/upload-avatar`,
      fd
    );
  },

  uploadBgImage: (shopId: string, platform: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<{ url: string; prompt: string }>(
      `/shops/${shopId}/profiles/${platform}/upload-bg-image`,
      fd
    );
  },

  cropAvatar: (shopId: string, platform: string, imageBase64: string) =>
    api.post<{ url: string }>(
      `/shops/${shopId}/profiles/${platform}/crop-avatar`,
      { image_base64: imageBase64 }
    ),

  cropBgImage: (shopId: string, platform: string, imageBase64: string) =>
    api.post<{ url: string }>(
      `/shops/${shopId}/profiles/${platform}/crop-bg-image`,
      { image_base64: imageBase64 }
    ),

  getColorSchemes: () =>
    api.get<ColorSchemePreset[]>("/color-schemes"),
};

