import type { DesignAsset } from "../services/designs";
import type { DeckTemplate, QaReport, StudioCopy } from "../services/studio";

export interface ThemePreset {
  key: string;
  label: string;
  paper: string;
  ink: string;
  accent: string;
}

export const EDITORIAL_THEMES: ThemePreset[] = [
  { key: "ink-classic", label: "墨色经典", paper: "#f3f0e8", ink: "#0a0a0b", accent: "#111111" },
  { key: "indigo-porcelain", label: "靛蓝青瓷", paper: "#f2f4f5", ink: "#0a1f3d", accent: "#315d93" },
  { key: "forest-ink", label: "森墨", paper: "#f5f1e8", ink: "#16251b", accent: "#2e6b4f" },
  { key: "kraft-paper", label: "牛皮纸", paper: "#eedfc7", ink: "#2a1e13", accent: "#9b5a2e" },
  { key: "dune", label: "沙丘", paper: "#f0e6d2", ink: "#1f1a14", accent: "#8f7650" },
  { key: "midnight-ink", label: "午夜墨", paper: "#0e0d0c", ink: "#ece2cf", accent: "#d4a04a" },
];

export const SWISS_THEMES: ThemePreset[] = [
  { key: "ikb-blue", label: "IKB 蓝", paper: "#fafaf8", ink: "#0a0a0a", accent: "#002FA7" },
  { key: "lemon-yellow", label: "柠檬黄", paper: "#fafaf8", ink: "#0a0a0a", accent: "#FFD500" },
  { key: "lemon-green", label: "柠檬绿", paper: "#fafaf8", ink: "#0a0a0a", accent: "#C5E803" },
  { key: "safety-orange", label: "安全橙", paper: "#fafaf8", ink: "#0a0a0a", accent: "#FF6B35" },
];

export function themeOptions(template: DeckTemplate): ThemePreset[] {
  return template === "swiss" ? SWISS_THEMES : EDITORIAL_THEMES;
}

export interface CopyFormValues {
  category: string;
  style: string;
  price_range: string;
  topic: string;
  shop_name: string;
}

export function validateCopyForm(values: CopyFormValues): string[] {
  const errors: string[] = [];
  if (!values.category.trim()) errors.push("品类不能为空");
  if (!values.style.trim()) errors.push("风格不能为空");
  if (!values.price_range.trim()) errors.push("价格带不能为空");
  if (!values.topic.trim()) errors.push("主题不能为空");
  if (!values.shop_name.trim()) errors.push("店名不能为空");
  return errors;
}

export function isCopyUsable(copy: StudioCopy | null | undefined): boolean {
  return !!copy && Array.isArray(copy.titles) && copy.titles.length > 0 && !!copy.body;
}

export function qaSummary(qa: QaReport | null | undefined): {
  allPass: boolean;
  passCount: number;
  total: number;
} {
  if (!qa || !Array.isArray(qa.pages)) return { allPass: false, passCount: 0, total: 0 };
  const passCount = qa.pages.filter((p) => p.pass).length;
  return { allPass: qa.all_pass, passCount, total: qa.pages.length };
}

export function clampPageCount(n: number): number {
  if (Number.isNaN(n)) return 4;
  return Math.min(8, Math.max(4, Math.round(n)));
}
export function toggleSelection<T>(
  selected: T[],
  item: T,
  isSame: (a: T, b: T) => boolean,
  max: number
): { items: T[]; added: boolean } {
  const has = selected.some((s) => isSame(s, item));
  if (has) return { items: selected.filter((s) => !isSame(s, item)), added: false };
  if (selected.length >= max) return { items: selected, added: false };
  return { items: [...selected, item], added: true };
}

export function addWithCap<T>(
  current: T[],
  incoming: T[],
  max: number
): { items: T[]; overflow: number } {
  const room = Math.max(0, max - current.length);
  return { items: [...current, ...incoming.slice(0, room)], overflow: Math.max(0, incoming.length - room) };
}
export function candidateToAsset(
  candidate: { aid: string; url: string; thumb_url: string | null; batch_id: string },
  projectId: string
): DesignAsset {
  return {
    id: candidate.aid,
    project_id: projectId,
    asset_type: "photo",
    source: "ai",
    status: "pending",
    batch_id: candidate.batch_id,
    derived_from_asset_id: null,
    original_url: candidate.url,
    processed_url: null,
    thumb_url: candidate.thumb_url,
    edit_stack: null,
    beauty_config: null,
    dish_name: null,
    price: null,
    tagline: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}
