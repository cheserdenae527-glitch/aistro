import api from "./api";

export interface CrawlTask {
  id: string;
  type: string;
  params: Record<string, unknown>;
  status: string;
  created_at: string;
  finished_at: string | null;
  result: {
    data?: unknown[];
    error?: string;
    stats?: Record<string, unknown>;
  } | null;
}

export const crawlJobService = {
  create: (jobType: string, params: Record<string, unknown>) =>
    api.post<{ job_id: string; status: string }>("/crawl-jobs", { job_type: jobType, params }),

  list: () =>
    api.get<{ running: CrawlTask[] }>("/crawl-jobs"),

  get: (jobId: string) =>
    api.get<CrawlTask>(`/crawl-jobs/${jobId}`),
};
