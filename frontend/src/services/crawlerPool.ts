import api from "./api";

export interface CookiePoolItem {
  id: string;
  label: string;
  cookie: string;
  status: "available" | "cooling" | "invalid" | "paused";
  use_count: number;
  success_count: number;
  fail_count: number;
  continuous_fail: number;
  last_used: number | null;
  last_success: number | null;
  cooling_until: number | null;
  last_error: string;
  proxy_session_id: string | null;
  proxy: {
    http: string;
    https: string;
    host?: string;
    port?: string;
    sid?: string;
  } | null;
  proxy_bound_at: number | null;
  proxy_expires_at: number | null;
  proxy_failures: number;
  created_at: string;
  updated_at: string;
}

export interface CookiePoolStats {
  total: number;
  counts: { available: number; cooling: number; invalid: number; paused: number };
  total_use: number;
  total_success: number;
  total_fail: number;
  config: {
    max_use_per_hour: number;
    max_continuous_fail: number;
    cooling_seconds: number;
    max_total_fail: number;
    proxy_session_seconds: number;
    max_proxy_failures: number;
  };
  usage_window_seconds: number;
  updated_at: string;
}

export interface ProxyPoolEntry {
  label: string;
  source: "tunnel" | "short_proxy" | "static";
}

export interface ProxyPoolStats {
  source: "tunnel" | "short_proxy" | "static" | "none";
  count: number;
  entries: ProxyPoolEntry[];
  tunnel_sids: string[];
  tunnel_period_seconds: string;
  tunnel_pool: string;
  short_proxy_refresh_seconds: number;
  static_count: number;
}

export interface CrawlCallRecord {
  ts_ms: number;
  channel: string;
  job_type: string;
  target: string;
  result: string;
  risk_type: string | null;
  error_message: string | null;
  latency_ms: number | null;
  interval_before_ms: number | null;
  proxy_used: string | null;
  cookie_id: string | null;
  cookie_label: string;
}

export const crawlerPoolService = {
  listCookies: () =>
    api.get<{ items: CookiePoolItem[]; stats: CookiePoolStats }>("/crawler/pool/cookies"),

  addCookie: (cookie: string, label: string) =>
    api.post<CookiePoolItem>("/crawler/pool/cookies", { cookie, label }),

  updateCookie: (id: string, patch: { cookie?: string; label?: string; status?: string }) =>
    api.patch<CookiePoolItem>(`/crawler/pool/cookies/${id}`, patch),

  deleteCookie: (id: string) =>
    api.delete<{ success: boolean }>(`/crawler/pool/cookies/${id}`),

  unbindCookie: (id: string) =>
    api.post<CookiePoolItem>(`/crawler/pool/cookies/${id}/unbind`),

  rebindCookie: (id: string) =>
    api.post<CookiePoolItem>(`/crawler/pool/cookies/${id}/rebind`),

  proxyStatus: () =>
    api.get<ProxyPoolStats>("/crawler/pool/proxies"),

  refreshProxies: () =>
    api.post<ProxyPoolStats>("/crawler/pool/proxies/refresh"),

  recentCalls: (limit = 50) =>
    api.get<{ items: CrawlCallRecord[] }>("/crawler/pool/calls", { params: { limit } }),
};
