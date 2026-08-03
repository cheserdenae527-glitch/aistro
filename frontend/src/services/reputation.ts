import api from "./api";

export type ReviewType = "note" | "comment" | "rating_review";
export type Sentiment = "positive" | "neutral" | "negative";
export type ReplyStatus = "unreplied" | "ai_replied" | "manual_replied";
export type AlertStatus = "none" | "triggered" | "acknowledged";

export interface AlertReason {
  type: "keyword" | "sentiment" | "both";
  keywords: string[];
  sentiment: Sentiment | null;
}

export interface Review {
  id: string;
  platform_shop_id: string;
  platform_review_id: string | null;
  reviewer_name: string | null;
  rating: number | null;
  content: string | null;
  tags: string[] | null;
  sentiment: Sentiment | null;
  reply_status: ReplyStatus | null;
  ai_reply: string | null;
  reply_content: string | null;
  replied_at: string | null;
  reviewed_at: string | null;
  review_type: ReviewType;
  parent_review_id: string | null;
  note_title: string | null;
  note_url: string | null;
  author_id: string | null;
  author_avatar: string | null;
  interact_stats: {
    liked?: number;
    collected?: number;
    comments?: number;
    shared?: number;
    [key: string]: number | undefined;
  } | null;
  source_json: Record<string, unknown> | null;
  alert_status: AlertStatus;
  alert_reason: AlertReason | null;
  created_at: string;
}

export interface ReviewListResponse {
  items: Review[];
  total: number;
  page: number;
  size: number;
}

export interface ReviewFilters {
  review_type?: ReviewType;
  sentiment?: Sentiment;
  reply_status?: ReplyStatus;
  alert_status?: AlertStatus;
  keyword?: string;
  parent_review_id?: string;
  date_from?: string;
  date_to?: string;
}

export type ReviewListParams = Record<string, string | number | undefined>;

export interface ReputationSummary {
  note_count: number;
  comment_count: number;
  rating_review_count: number;
  sentiment_counts: Record<string, number>;
  unreplied_count: number;
  alert_count: number;
}

export interface BatchAnalyzeItem {
  id: string;
  sentiment: Sentiment;
  tags: string[];
}

export interface BatchAnalyzeResponse {
  analyzed: BatchAnalyzeItem[];
  failed: string[];
  total: number;
  success_count: number;
  failed_count: number;
}

export interface SyncResponse {
  created: number;
  skipped: number;
}

export interface AiReplyResponse {
  id: string;
  ai_reply: string;
  reply_status: ReplyStatus;
}

export const reputationService = {
  listReviews: (shopId: string, params?: ReviewListParams) =>
    api.get<ReviewListResponse>(`/shops/${shopId}/reviews`, { params }),

  getSummary: (shopId: string) =>
    api.get<ReputationSummary>(`/shops/${shopId}/reviews/summary`),

  syncNotes: (shopId: string, keyword: string, limit: number) =>
    api.post<SyncResponse>(`/shops/${shopId}/reviews/sync/xiaohongshu`, {
      keyword,
      limit,
    }),

  syncComments: (shopId: string, reviewId: string) =>
    api.post<SyncResponse>(`/shops/${shopId}/reviews/${reviewId}/sync-comments`),

  batchAnalyze: (shopId: string, reviewIds: string[]) =>
    api.post<BatchAnalyzeResponse>(`/shops/${shopId}/reviews/batch-analyze`, {
      review_ids: reviewIds,
    }),

  aiReply: (shopId: string, reviewId: string) =>
    api.post<AiReplyResponse>(`/shops/${shopId}/reviews/${reviewId}/ai-reply`),

  submitReply: (shopId: string, reviewId: string, replyContent: string) =>
    api.put<Review>(`/shops/${shopId}/reviews/${reviewId}/reply`, {
      reply_content: replyContent,
    }),

  listAlerts: (shopId: string) =>
    api.get<Review[]>(`/shops/${shopId}/reviews/alerts`),

  ackAlert: (shopId: string, reviewId: string) =>
    api.post<{ id: string; alert_status: AlertStatus }>(
      `/shops/${shopId}/reviews/alerts/${reviewId}/ack`
    ),
};
