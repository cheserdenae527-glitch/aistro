import type {
  ComplianceItem,
  LiveScript,
  LiveSession,
  ScriptSegmentType,
} from "../services/live";

export const PLATFORM_LABELS: Record<string, string> = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  wechat: "视频号",
};

export const SEGMENT_TYPE_LABELS: Record<ScriptSegmentType, string> = {
  opening: "开场留人",
  product: "产品介绍",
  promo: "优惠逼单",
  interaction: "互动",
  qa: "答疑",
  closing: "收尾",
};

export const SEGMENT_TYPE_ORDER: ScriptSegmentType[] = [
  "opening",
  "product",
  "promo",
  "interaction",
  "qa",
  "closing",
];

export const SCRIPT_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  edited: "已编辑",
  confirmed: "已定稿",
};

export const SCRIPT_STATUS_COLORS: Record<string, string> = {
  draft: "default",
  edited: "blue",
  confirmed: "green",
};

export const SESSION_STATUS_LABELS: Record<string, string> = {
  planned: "待开播",
  live: "直播中",
  ended: "已结束",
  cancelled: "已取消",
};

export const SESSION_STATUS_COLORS: Record<string, string> = {
  planned: "blue",
  live: "red",
  ended: "default",
  cancelled: "default",
};

export const AVATAR_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  ready: "就绪",
  disabled: "停用",
};

export const AVATAR_STATUS_COLORS: Record<string, string> = {
  draft: "default",
  ready: "green",
  disabled: "red",
};

export const REPLY_MODE_LABELS: Record<string, string> = {
  auto: "自动",
  manual: "人工",
};

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return "-";
  }
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} 秒`;
  const min = Math.floor(total / 60);
  const sec = total % 60;
  if (min >= 60) {
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m > 0 ? `${h} 小时 ${m} 分` : `${h} 小时`;
  }
  return sec > 0 ? `${min} 分 ${sec} 秒` : `${min} 分钟`;
}

export function formatDurationShort(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return "-";
  }
  return `${Math.round(seconds)}s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

/** 当前活跃批次脚本（is_archived=false，batch 最大） */
export function activeScript(scripts: LiveScript[] | null | undefined): LiveScript | null {
  if (!scripts || scripts.length === 0) return null;
  const active = scripts
    .filter((s) => !s.is_archived)
    .sort((a, b) => b.generation_batch - a.generation_batch);
  return active[0] ?? null;
}

/** 最新批次脚本（含归档） */
export function latestScript(scripts: LiveScript[] | null | undefined): LiveScript | null {
  if (!scripts || scripts.length === 0) return null;
  return [...scripts].sort((a, b) => b.generation_batch - a.generation_batch)[0];
}

/** 已有活跃批次或已定稿脚本 → regenerate 需二次确认 */
export function shouldConfirmRegenerate(scripts: LiveScript[] | null | undefined): boolean {
  if (!scripts || scripts.length === 0) return false;
  return scripts.some((s) => !s.is_archived || s.status === "confirmed");
}

/** 仅当前活跃批次的 confirmed 脚本可导出 */
export function canExport(script: LiveScript | null | undefined): boolean {
  return !!script && !script.is_archived && script.status === "confirmed";
}

/** 脚本是否已定稿（含已归档） */
export function isConfirmed(script: LiveScript | null | undefined): boolean {
  return !!script && script.status === "confirmed";
}

export function complianceFailures(items: ComplianceItem[] | null | undefined): ComplianceItem[] {
  return (items ?? []).filter((i) => !i.ok);
}

export function complianceWarnings(items: ComplianceItem[] | null | undefined): ComplianceItem[] {
  return (items ?? []).filter((i) => i.ok && /提示|未配置|建议|占位/.test(i.detail));
}

export function scriptSegments(script: LiveScript | null | undefined): LiveScript["content"] {
  return script?.content ?? [];
}

export function totalDuration(script: LiveScript | null | undefined): number {
  return (script?.content ?? []).reduce((sum, s) => sum + (s.duration_sec || 0), 0);
}

/** 场次脚本名（纯人工直播标注） */
export function sessionScriptLabel(session: LiveSession, scripts: LiveScript[]): string {
  if (!session.script_id) return "纯人工直播（无脚本）";
  const s = scripts.find((x) => x.id === session.script_id);
  return s ? s.title : "脚本已移除";
}

export function isTerminal(status: string): boolean {
  return status === "ended" || status === "cancelled";
}

export function formatGmv(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `¥${Number(value).toFixed(2)}`;
}
