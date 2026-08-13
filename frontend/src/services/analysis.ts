// frontend/src/services/analysis.ts
import api from './api';

export type Recommendation = 'priority' | 'ok' | 'caution' | 'not_recommended' | 'insufficient_data';
export type StageLabel = '冷启动' | '成长' | '成熟' | '衰退';
export type Conf = 'high' | 'medium' | 'low';
export type TaskStatus = 'pending' | 'running' | 'success' | 'partial' | 'failed' | 'cancelled';

export interface DimensionDetail {
  collect_rate_percent?: number;
  collect_like_ratio?: number;
  share_rate_percent?: number;
  comment_signal?: number;
  comment_signal_low_conf?: boolean;
  food_ratio?: number;
  food_notes?: number;
  judged_notes?: number;
  viral_ratio?: number;
  gap_days?: number;
  cliff_detected?: boolean;
  weekly_notes?: number;
  freshness_days?: number;
  growth_rate?: number | null;
  has_snapshot?: boolean;
  suggested_bid_picture?: number | null;
  suggested_bid_video?: number | null;
  suggested_range_picture?: [number, number] | null;
  suggested_range_video?: [number, number] | null;
  trend_ratio?: number | null;
  reason?: string | null;
}

export interface BloggerDimension {
  score: number | null;
  confidence: Conf;
  detail: DimensionDetail;
}

export interface BloggerAnalysisResult {
  note_count: number;
  real_note_count: number;
  sampled: boolean;                                   // 顶层，匹配后端
  coverage: { total_notes: number; sample_size: number; fetched_notes: number; coverage_rate: number };
  confidence: Conf;
  dimensions: Record<'seeding_depth' | 'verticality' | 'stable_output' | 'sustained_operation' | 'growth_trend' | 'cost_effectiveness', BloggerDimension>;
  overall: { score: number | null; level: string; description: string; score_suppressed: boolean } | null;
  audience?: {
    dominant_level: string | null;
    level_distribution: Record<string, number>;
    avg_price_band: [number, number] | null;
    top_categories: string[];
    top_scenes: string[];
    merchant_tiers: string[];
    signal_notes: number;
    confidence: string;
    verticality_audience_score: number;
    match?: { has_profile: boolean; score: number | null; sub_scores: Record<string, number>; mismatches: string[] };
  } | null;
  overall_score_suppressed?: boolean;
  stage: { label: StageLabel; confidence: Conf; evidence: string[] } | null;
  decision: {
    recommendation: Recommendation;
    summary: string;
    reasons: string[];
    red_flags: { type: string; level: string; detail: string }[];
    low_quality: boolean;
  } | null;
  insights: string[];
  anomalies: { type: string; level: string; detail: string }[];
  notes: any[];
  timeline: { items?: any[] };
  follower_history: any;
  grass_planting: any;
  growth_potential: any;
}

export interface ScreeningRow {
  user_id: string;
  nickname: string;
  fans: number;
  overall_score: number | null;
  score_suppressed: boolean;
  level: string;
  recommendation: Recommendation;
  stage_label: StageLabel | '-';
  stage_confidence: Conf;
  red_flags: string[];
  collect_rate: number | null;
  food_ratio: number | null;
  confidence: Conf;
}

// 任务包裹（后端 _task_payload，notes.py）：分析结果在 .result，非直接结果
export interface AnalysisTaskPayload {
  id: string;
  xhs_user_id: string;
  nickname: string;
  follower_count: number;
  status: TaskStatus;
  prescreen_passed: boolean;
  prescreen_reason: string | null;
  total_notes: number;
  target_notes: number;
  fetched_notes: number;
  coverage: number | null;
  confidence: Conf | null;
  with_comments: boolean;
  result: BloggerAnalysisResult | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

// 粗筛未通过：POST 不创建任务，直接返回失败原因
export type CreateAnalysisTaskResponse =
  | AnalysisTaskPayload
  | { passed_prescreen: false; reason: string; fans: number; notes: number; avg_likes: number };

// 注意：本文件函数直接返回 response.data（已解包），与 merchants/deals 等直接返回 AxiosResponse 的服务不同。
/** 返回任务包裹（analysis 在 .result），非直接结果 */
export async function fetchAnalysisTask(userId: string, taskId: string): Promise<AnalysisTaskPayload> {
  return (await api.get(`/notes/users/${userId}/analysis-tasks/${taskId}`)).data;
}

export async function createAnalysisTask(
  userId: string,
  payload: { nickname: string; fans: number; with_comments?: boolean },
): Promise<CreateAnalysisTaskResponse> {
  return (await api.post(`/notes/users/${userId}/analysis-tasks`, payload, { timeout: 60000 })).data;
}

export async function listAnalysisTasks(
  params?: { status?: string; limit?: number; ids?: string[] },
): Promise<{ items: AnalysisTaskPayload[] }> {
  const query: Record<string, string | number> = {};
  if (params?.status) query.status = params.status;
  if (params?.limit != null) query.limit = params.limit;
  if (params?.ids?.length) query.ids = params.ids.join(',');
  return (await api.get('/notes/analysis-tasks', { params: query })).data;
}

// ---------- 批量分析 ----------
export interface BatchBloggerInput {
  user_id: string;
  nickname?: string;
  fans?: number;
  with_comments?: boolean;
}

export interface BatchCreatedItem {
  task_id: string;
  xhs_user_id: string;
  nickname: string;
  status: string;
  follower_count?: number;
  notes?: number;
}

export interface BatchRejectedItem {
  xhs_user_id: string;
  nickname: string;
  reason: string;
}

export interface BatchCreateResponse {
  created: BatchCreatedItem[];
  rejected: BatchRejectedItem[];
}

/** 批量创建博主分析任务：后端逐博主真实粗筛，通过者创建后台任务（单次上限 50）。 */
export async function exportAnalysisReport(): Promise<Blob> {
  const res = await api.get('/notes/analysis-tasks/export', { responseType: 'blob', timeout: 60000 });
  return res.data;
}

export async function createAnalysisTasksBatch(bloggers: BatchBloggerInput[]): Promise<BatchCreateResponse> {
  return (await api.post('/notes/analysis-tasks/batch', { bloggers }, { timeout: 300000 })).data;
}

export interface AnalysisSummary {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  cooperate: boolean;
  cooperate_reason: string;
}

export async function getAnalysisSummary(taskId: string): Promise<AnalysisSummary> {
  return (await api.post(`/notes/analysis-tasks/${taskId}/summary`, undefined, { timeout: 60000 })).data;
}
