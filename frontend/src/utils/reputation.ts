import type {
  ReplyStatus,
  ReviewFilters,
  Sentiment,
} from "../services/reputation";

export const MAX_BATCH_ANALYZE = 20;

export interface ReviewQueryParams {
  [key: string]: string | number | undefined;
  review_type?: string;
  sentiment?: string;
  reply_status?: string;
  alert_status?: string;
  keyword?: string;
  parent_review_id?: string;
  date_from?: string;
  date_to?: string;
  page: number;
  size: number;
}

export function buildReviewParams(
  filters: ReviewFilters,
  page: number,
  size: number
): ReviewQueryParams {
  const params: ReviewQueryParams = { page, size };
  if (filters.review_type) params.review_type = filters.review_type;
  if (filters.sentiment) params.sentiment = filters.sentiment;
  if (filters.reply_status) params.reply_status = filters.reply_status;
  if (filters.alert_status) params.alert_status = filters.alert_status;
  if (filters.keyword) params.keyword = filters.keyword;
  if (filters.parent_review_id) params.parent_review_id = filters.parent_review_id;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  return params;
}

export function toggleSelection(
  selected: string[],
  id: string
): { ids: string[]; rejected: boolean } {
  if (selected.includes(id)) {
    return { ids: selected.filter((item) => item !== id), rejected: false };
  }
  if (selected.length >= MAX_BATCH_ANALYZE) {
    return { ids: selected, rejected: true };
  }
  return { ids: [...selected, id], rejected: false };
}

export function replyStatusMeta(status: ReplyStatus | null): {
  label: string;
  color: string;
} {
  switch (status) {
    case "unreplied":
      return { label: "未回复", color: "default" };
    case "ai_replied":
      return { label: "AI 草稿", color: "blue" };
    case "manual_replied":
      return { label: "已回复", color: "green" };
    default:
      return { label: "无需回复", color: "default" };
  }
}

export function sentimentMeta(sentiment: Sentiment | null): {
  label: string;
  color: string;
} {
  switch (sentiment) {
    case "positive":
      return { label: "正面", color: "green" };
    case "neutral":
      return { label: "中性", color: "blue" };
    case "negative":
      return { label: "负面", color: "red" };
    default:
      return { label: "未分析", color: "default" };
  }
}
