import type { DealPlatform, DealScheme, DealSchemeCopy, MarginEstimate } from "../services/deals";

export const PLATFORMS: DealPlatform[] = ["douyin", "meituan", "xiaohongshu"];

export const PLATFORM_LABELS: Record<string, string> = {
  douyin: "抖音",
  meituan: "美团",
  xiaohongshu: "小红书",
};

export const CATEGORY_LABELS: Record<string, string> = {
  signature: "招牌",
  staple: "主食",
  snack: "小吃",
  drink: "饮品",
};

export const SCHEME_TYPE_LABELS: Record<string, string> = {
  hook: "引流款",
  profit: "利润款",
  scenario: "场景款",
};

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function formatPrice(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  return Number.isNaN(n) ? "-" : `¥${n.toFixed(2)}`;
}

export function marginLines(margin: MarginEstimate | null | undefined): {
  gross: string;
  net: string;
  rate: string;
  note: string;
} {
  if (!margin) return { gross: "-", net: "-", rate: "-", note: "" };
  return {
    gross: percent(margin.gross_margin),
    net: percent(margin.net_margin),
    rate: percent(margin.platform_commission_rate),
    note: margin.note || "",
  };
}

export function hasActiveSchemes(schemes: DealScheme[]): boolean {
  return schemes.some((s) => !s.is_archived);
}

export function hasEditedScheme(schemes: DealScheme[]): boolean {
  return schemes.some((s) => !s.is_archived && s.status === "edited");
}

export function shouldConfirmRegenerate(schemes: DealScheme[]): boolean {
  return hasActiveSchemes(schemes) || hasEditedScheme(schemes);
}

export function copyForPlatform(
  scheme: DealScheme,
  platform: string
): DealSchemeCopy | undefined {
  return (scheme.copies ?? []).find((c) => c.platform === platform);
}

export function schemeItemLines(scheme: DealScheme): string {
  return (scheme.items ?? [])
    .map((it) => `${it.name} ×${it.qty}`)
    .join(" + ");
}

export function schemeSummary(scheme: DealScheme): string {
  const lines = [
    `组合：${schemeItemLines(scheme) || "-"}`,
    `原价 ${formatPrice(scheme.original_price)} → 团购价 ${formatPrice(scheme.deal_price)}`,
  ];
  return lines.join("\n");
}

export function buildCopyClipboardText(copy: DealSchemeCopy | undefined): string {
  if (!copy) return "";
  const points = (copy.selling_points ?? []).map((p) => `- ${p}`).join("\n");
  return [copy.title, points, copy.rules ? `规则：${copy.rules}` : ""]
    .filter(Boolean)
    .join("\n\n");
}
