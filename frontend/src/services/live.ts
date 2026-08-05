import api from "./api";

export type LivePlatform = "douyin" | "xiaohongshu" | "wechat";
export type LiveProjectStatus = "draft" | "active" | "archived";
export type AvatarType = "image" | "video";
export type AvatarStatus = "draft" | "ready" | "disabled";
export type ScriptSegmentType =
  | "opening"
  | "product"
  | "promo"
  | "interaction"
  | "qa"
  | "closing";
export type ScriptStatus = "draft" | "edited" | "confirmed";
export type SessionStatus = "planned" | "live" | "ended" | "cancelled";
export type ReplyMode = "auto" | "manual";

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface EngineConfig {
  base_url?: string | null;
  enabled?: boolean | null;
  last_health_check?: string | null;
  api_key_configured?: boolean;
}

export interface EnginePushResult {
  status: "ok" | "skipped" | "failed";
  detail: string;
}

export interface EngineTestResult {
  ok: boolean;
  base_url: string;
  health: {
    ok: boolean;
    status_code: number;
    latency_ms: number;
    detail: string;
  } | null;
  persona_push: EnginePushResult | null;
  wordlist_push: EnginePushResult | null;
  last_health_check: string | null;
  error?: string | null;
}

export interface EngineTestRequest {
  base_url?: string | null;
  push_persona?: boolean;
  push_wordlist?: boolean;
  persona_json?: Persona | null;
  wordlist?: string[] | null;
}

export interface PromoItem {
  name: string;
  price?: number | null;
  original_price?: number | null;
  rules?: string | null;
  link?: string | null;
}

export interface LiveProject {
  id: string;
  shop_id: string;
  title: string;
  platform: LivePlatform;
  goal: string | null;
  promo_items: PromoItem[] | null;
  ai_label_text: string | null;
  engine_config: EngineConfig | null;
  status: LiveProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface VoiceConfig {
  provider?: string | null;
  voice?: string | null;
  speed?: number | null;
  pitch?: number | null;
}

export interface Persona {
  identity?: string;
  tone?: string;
  boundaries?: string;
  forbidden_topics?: string[];
  [key: string]: unknown;
}

export interface LiveAvatar {
  id: string;
  org_id: string;
  name: string;
  avatar_type: AvatarType;
  image_url: string | null;
  video_url: string | null;
  voice_config: VoiceConfig | null;
  persona: Persona | null;
  status: AvatarStatus;
  created_at: string;
  updated_at: string;
}

export interface ScriptSegment {
  type: ScriptSegmentType;
  title: string;
  text: string;
  duration_sec: number;
  cue: string | null;
}

export interface ComplianceItem {
  key: string;
  ok: boolean;
  detail: string;
}

export interface ComplianceResult {
  pass: boolean;
  items: ComplianceItem[];
}

export interface LiveScript {
  id: string;
  project_id: string;
  avatar_id: string | null;
  persona_snapshot: Persona | null;
  generation_batch: number;
  title: string;
  tone: string | null;
  content: ScriptSegment[] | null;
  total_duration_sec: number | null;
  status: ScriptStatus;
  is_archived: boolean;
  compliance: ComplianceResult | null;
  created_at: string;
  updated_at: string;
}

export interface ReplyRule {
  trigger: string;
  reply: string;
  mode: ReplyMode;
}

export interface LiveDanmakuConfig {
  id: string;
  project_id: string;
  source_script_id: string | null;
  persona: Persona | null;
  reply_rules: ReplyRule[] | null;
  sensitive_words: string[] | null;
  escalate_topics: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface LiveSession {
  id: string;
  project_id: string;
  script_id: string | null;
  avatar_id: string | null;
  scheduled_at: string;
  duration_min: number | null;
  status: SessionStatus;
  operator_id: string | null;
  duty_confirmed: boolean;
  ai_label_confirmed: boolean;
  is_backfilled: boolean;
  notes: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionMetrics {
  viewers?: number | null;
  peak_viewers?: number | null;
  avg_watch_sec?: number | null;
  interaction_count?: number | null;
  danmaku_count?: number | null;
  order_count?: number | null;
  gmv?: number | null;
  redemption_count?: number | null;
  note?: string | null;
}

export interface LiveSessionMetric {
  id: string;
  session_id: string;
  metrics: SessionMetrics | null;
  source: "manual" | "import";
  ai_review: string | null;
  created_at: string;
  updated_at: string;
}

export interface LiveExportBundle {
  script_markdown: string;
  persona_json: Persona;
  wordlist: string[];
  reply_rules: ReplyRule[];
  compliance: ComplianceResult;
  engine_guide: string;
}

export interface LiveProjectCreate {
  shop_id: string;
  title: string;
  platform: LivePlatform;
  goal?: string | null;
  promo_items?: PromoItem[] | null;
  ai_label_text?: string | null;
  engine_config?: EngineConfig | null;
}

export interface LiveProjectUpdate {
  title?: string;
  platform?: LivePlatform;
  goal?: string | null;
  promo_items?: PromoItem[] | null;
  ai_label_text?: string | null;
  engine_config?: EngineConfig | null;
  status?: LiveProjectStatus;
}

export interface LiveAvatarCreate {
  name: string;
  avatar_type?: AvatarType;
  image_url?: string | null;
  video_url?: string | null;
  voice_config?: VoiceConfig | null;
  persona?: Persona | null;
  status?: AvatarStatus;
}

export interface LiveAvatarUpdate {
  name?: string;
  avatar_type?: AvatarType;
  image_url?: string | null;
  video_url?: string | null;
  voice_config?: VoiceConfig | null;
  persona?: Persona | null;
  status?: AvatarStatus;
}

export interface ScriptGenerateRequest {
  tone?: string | null;
  duration_min?: number | null;
  avatar_id?: string | null;
}

export interface ScriptUpdateRequest {
  title?: string;
  tone?: string | null;
  content?: ScriptSegment[];
  total_duration_sec?: number;
}

export interface DanmakuConfigUpdate {
  persona?: Persona | null;
  reply_rules?: ReplyRule[] | null;
  sensitive_words?: string[] | null;
  escalate_topics?: string[] | null;
}

export interface LiveSessionCreate {
  script_id?: string | null;
  avatar_id?: string | null;
  scheduled_at: string;
  duration_min?: number | null;
  operator_id?: string | null;
  notes?: string | null;
}

export interface LiveSessionUpdate {
  script_id?: string | null;
  avatar_id?: string | null;
  scheduled_at?: string;
  duration_min?: number | null;
  operator_id?: string | null;
  notes?: string | null;
  duty_confirmed?: boolean;
  ai_label_confirmed?: boolean;
  status?: SessionStatus;
  started_at?: string;
  ended_at?: string;
}

export interface MetricsCreate {
  metrics: SessionMetrics;
  source?: "manual" | "import";
}

export const liveService = {
  // ---- 项目 ----
  listProjects: (params?: { shop_id?: string; page?: number; page_size?: number }) =>
    api.get<Paginated<LiveProject>>("/live-projects", { params }),
  getProject: (id: string) => api.get<LiveProject>(`/live-projects/${id}`),
  createProject: (data: LiveProjectCreate) => api.post<LiveProject>("/live-projects", data),
  updateProject: (id: string, data: LiveProjectUpdate) =>
    api.patch<LiveProject>(`/live-projects/${id}`, data),
  deleteProject: (id: string) => api.delete<{ ok: boolean }>(`/live-projects/${id}`),
  engineTest: (id: string, data?: EngineTestRequest) =>
    api.post<EngineTestResult>(`/live-projects/${id}/engine-test`, data ?? {}, {
      timeout: 30_000,
    }),

  // ---- 数字人形象（org 维度） ----
  listAvatars: (params?: { page?: number; page_size?: number }) =>
    api.get<Paginated<LiveAvatar>>("/live-avatars", { params }),
  createAvatar: (data: LiveAvatarCreate) => api.post<LiveAvatar>("/live-avatars", data),
  updateAvatar: (id: string, data: LiveAvatarUpdate) =>
    api.patch<LiveAvatar>(`/live-avatars/${id}`, data),
  deleteAvatar: (id: string) => api.delete<{ ok: boolean }>(`/live-avatars/${id}`),

  // ---- 直播脚本 ----
  generateScript: (projectId: string, data: ScriptGenerateRequest) =>
    api.post<LiveScript>(`/live-projects/${projectId}/scripts/generate`, data, {
      timeout: 120_000,
    }),
  listScripts: (projectId: string, includeArchived = false) =>
    api.get<LiveScript[]>(`/live-projects/${projectId}/scripts`, {
      params: { include_archived: includeArchived },
    }),
  getScript: (projectId: string, sid: string) =>
    api.get<LiveScript>(`/live-projects/${projectId}/scripts/${sid}`),
  updateScript: (projectId: string, sid: string, data: ScriptUpdateRequest) =>
    api.put<LiveScript>(`/live-projects/${projectId}/scripts/${sid}`, data),
  confirmScript: (projectId: string, sid: string) =>
    api.post<LiveScript>(`/live-projects/${projectId}/scripts/${sid}/confirm`),
  deleteScript: (projectId: string, sid: string) =>
    api.delete<{ ok: boolean }>(`/live-projects/${projectId}/scripts/${sid}`),
  exportScript: (projectId: string, sid: string) =>
    api.post<LiveExportBundle>(`/live-projects/${projectId}/scripts/${sid}/export`),

  // ---- 弹幕互动 ----
  generateDanmaku: (projectId: string) =>
    api.post<LiveDanmakuConfig>(`/live-projects/${projectId}/danmaku-config/generate`, {}, { timeout: 120_000 }),
  getDanmaku: (projectId: string) =>
    api.get<LiveDanmakuConfig>(`/live-projects/${projectId}/danmaku-config`),
  updateDanmaku: (projectId: string, data: DanmakuConfigUpdate) =>
    api.put<LiveDanmakuConfig>(`/live-projects/${projectId}/danmaku-config`, data),

  // ---- 合规自检 ----
  complianceCheck: (projectId: string, scriptId?: string) =>
    api.post<ComplianceResult>(`/live-projects/${projectId}/compliance/check`, {
      script_id: scriptId ?? undefined,
    }),

  // ---- 场次 ----
  createSession: (projectId: string, data: LiveSessionCreate) =>
    api.post<LiveSession>(`/live-projects/${projectId}/sessions`, data),
  listSessions: (projectId: string, params?: { page?: number; page_size?: number }) =>
    api.get<Paginated<LiveSession>>(`/live-projects/${projectId}/sessions`, { params }),
  getSession: (projectId: string, sid: string) =>
    api.get<LiveSession>(`/live-projects/${projectId}/sessions/${sid}`),
  updateSession: (projectId: string, sid: string, data: LiveSessionUpdate) =>
    api.patch<LiveSession>(`/live-projects/${projectId}/sessions/${sid}`, data),
  deleteSession: (projectId: string, sid: string) =>
    api.delete<{ ok: boolean }>(`/live-projects/${projectId}/sessions/${sid}`),

  // ---- 复盘 ----
  upsertMetrics: (projectId: string, sid: string, data: MetricsCreate) =>
    api.post<LiveSessionMetric>(`/live-projects/${projectId}/sessions/${sid}/metrics`, data),
  getMetrics: (projectId: string, sid: string) =>
    api.get<LiveSessionMetric>(`/live-projects/${projectId}/sessions/${sid}/metrics`),
  reviewSession: (projectId: string, sid: string) =>
    api.post<{ ai_review: string }>(`/live-projects/${projectId}/sessions/${sid}/review`, {}, { timeout: 120_000 }),
};
