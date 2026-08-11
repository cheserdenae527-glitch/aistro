// frontend/src/services/analysis.ts
import api from './api';

export type Recommendation = 'priority' | 'ok' | 'caution' | 'not_recommended' | 'insufficient_data';
export type StageLabel = '冷启动' | '成长' | '成熟' | '衰退';
export type Conf = 'high' | 'medium' | 'low';

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
  coverage: { total_notes: number; fetched_notes: number; coverage_rate: number; sampled: boolean };
  confidence: Conf;
  dimensions: Record<'seeding_depth' | 'verticality' | 'stable_output' | 'sustained_operation' | 'growth_trend', BloggerDimension>;
  overall: { score: number | null; level: string; description: string; score_suppressed: boolean } | null;
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
  avatar: string;
  fans: number;
  overall_score: number | null;
  score_suppressed: boolean;
  level: string;
  recommendation: Recommendation;
  stage_label: StageLabel;
  stage_confidence: Conf;
  red_flags: string[];
  collect_rate: number;
  confidence: Conf;
}

export async function fetchAnalysisTask(userId: string, taskId: string): Promise<any> {
  return (await api.get(`/notes/users/${userId}/analysis-tasks/${taskId}`)).data;
}

export async function createAnalysisTask(userId: string, payload: { nickname: string; fans: number; with_comments?: boolean }): Promise<any> {
  return (await api.post(`/notes/users/${userId}/analysis-tasks`, payload, { timeout: 60000 })).data;
}
