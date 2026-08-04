export type FilterPreset = "none" | "warm" | "japanese" | "vivid" | "bw" | "film" | "tealOrange" | "cool" | "soft" | "moody" | "fresh";

export interface CropRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TextLabel {
  id: string;
  text: string;
  x: number;
  y: number;
  size: number;
  color: string;
}

export interface EditorSettings {
  crop: CropRect | null;
  outputSize: { width: number; height: number } | null;
  rotation: number;
  brightness: number;
  contrast: number;
  saturation: number;
  temperature: number;
  filter: FilterPreset;
  filterStrength: number;
  texts: TextLabel[];
}

export const DEFAULT_SETTINGS: EditorSettings = {
  crop: null,
  outputSize: null,
  rotation: 0,
  brightness: 100,
  contrast: 100,
  saturation: 100,
  temperature: 0,
  filter: "none",
  filterStrength: 100,
  texts: [],
};

/** 历史快照：编辑参数 + 当前源图，保证换源操作（美化/AI 候选）也能撤销。 */
export interface EditorSnapshot {
  settings: EditorSettings;
  sourceUrl: string | null;
}

export interface HistoryState<T> {
  past: T[];
  present: T;
  future: T[];
}

export function createHistory<T = EditorSettings>(
  initial: T = DEFAULT_SETTINGS as T
): HistoryState<T> {
  return { past: [], present: initial, future: [] };
}

export function createEditorHistory(
  sourceUrl: string | null
): HistoryState<EditorSnapshot> {
  return createHistory<EditorSnapshot>({
    settings: { ...DEFAULT_SETTINGS },
    sourceUrl,
  });
}

/** 提交一个可撤销的编辑动作。 */
export function commit<T>(state: HistoryState<T>, next: T): HistoryState<T> {
  return {
    past: [...state.past, state.present].slice(-100),
    present: next,
    future: [],
  };
}

/** 连续参数调整（滑块拖动中）：只改当前状态，不产生新历史节点。 */
export function replace<T>(state: HistoryState<T>, next: T): HistoryState<T> {
  return { ...state, present: next };
}

export function undo<T>(state: HistoryState<T>): HistoryState<T> {
  if (state.past.length === 0) return state;
  const previous = state.past[state.past.length - 1];
  return {
    past: state.past.slice(0, -1),
    present: previous,
    future: [state.present, ...state.future].slice(0, 100),
  };
}

export function redo<T>(state: HistoryState<T>): HistoryState<T> {
  if (state.future.length === 0) return state;
  const [next, ...rest] = state.future;
  return {
    past: [...state.past, state.present].slice(-100),
    present: next,
    future: rest,
  };
}

/** 序列化为后端 edit_stack（白名单字段，保持可回放）。 */
export function serializeSettings(settings: EditorSettings): Record<string, unknown> {
  return {
    crop: settings.crop,
    outputSize: settings.outputSize,
    rotation: settings.rotation,
    brightness: settings.brightness,
    contrast: settings.contrast,
    saturation: settings.saturation,
    temperature: settings.temperature,
    filter: settings.filter,
    filterStrength: settings.filterStrength,
    texts: settings.texts.map((t) => ({ ...t })),
  };
}

export function clampSlider(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}