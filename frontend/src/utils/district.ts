// 商圈分析展示辅助函数（纯逻辑，便于单测）
import type { CategoryStat, SnapshotSummary } from "../services/district";

/** 商圈密度格式化：家/km²，保留两位小数。null/无意义返回 —。 */
export function formatDensity(density: number | null | undefined): string {
  if (density === null || density === undefined || Number.isNaN(density)) return "—";
  return `${density.toFixed(2)} 家/km²`;
}

/** 品类数：无统计返回 0。 */
export function categoryCount(stats: CategoryStat[] | null | undefined): number {
  if (!Array.isArray(stats) || stats.length === 0) return 0;
  return stats.length;
}

/** 品类分布按数量降序排序（不修改入参）。 */
export function sortCategoryStats(
  stats: CategoryStat[] | null | undefined
): CategoryStat[] {
  if (!Array.isArray(stats)) return [];
  return [...stats].sort((a, b) => b.count - a.count);
}

/** 距离格式化：<1000m 显示米，否则显示公里（1 位小数）。 */
export function formatDistance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined || Number.isNaN(meters)) return "—";
  if (meters < 1000) return `${Math.round(meters)}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}

/** 时间格式化：YYYY-MM-DD HH:mm */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 判断快照是否可展示地图（成功且含中心坐标）。 */
export function hasMapData(snapshot: SnapshotSummary | null | undefined): boolean {
  return (
    !!snapshot &&
    snapshot.status === "analyzed" &&
    typeof snapshot.center_lng === "number" &&
    typeof snapshot.center_lat === "number"
  );
}

/** 429 倒计时：从当前秒数向下取整，最小 0。 */
export function countdownText(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return `${mm}:${String(ss).padStart(2, "0")}`;
}

/** 计算 429 冷却剩余秒数（基于初始等待秒数与已等待秒数）。 */
export function remainingCooldown(totalSeconds: number, elapsedSeconds: number): number {
  return Math.max(0, totalSeconds - Math.max(0, Math.floor(elapsedSeconds)));
}
