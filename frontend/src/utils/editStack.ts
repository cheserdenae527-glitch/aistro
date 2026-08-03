export type FilterPreset = "none" | "warm" | "japanese" | "vivid" | "bw";

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
  rotation: number;
  brightness: number;
  contrast: number;
  saturation: number;
  temperature: number;
  filter: FilterPreset;
  texts: TextLabel[];
}

export const DEFAULT_SETTINGS: EditorSettings = {
  crop: null,
  rotation: 0,
  brightness: 100,
  contrast: 100,
  saturation: 100,
  temperature: 0,
  filter: "none",
  texts: [],
};

export interface HistoryState {
  past: EditorSettings[];
  present: EditorSettings;
  future: EditorSettings[];
}

export function createHistory(initial: EditorSettings = DEFAULT_SETTINGS): HistoryState {
  return { past: [], present: initial, future: [] };
}

/** 提交一个可撤销的编辑动作。 */
export function commit(state: HistoryState, next: EditorSettings): HistoryState {
  return {
    past: [...state.past, state.present].slice(-100),
    present: next,
    future: [],
  };
}

/** 连续参数调整（滑块拖动中）：只改当前状态，不产生新历史节点。 */
export function replace(state: HistoryState, next: EditorSettings): HistoryState {
  return { ...state, present: next };
}

export function undo(state: HistoryState): HistoryState {
  if (state.past.length === 0) return state;
  const previous = state.past[state.past.length - 1];
  return {
    past: state.past.slice(0, -1),
    present: previous,
    future: [state.present, ...state.future].slice(0, 100),
  };
}

export function redo(state: HistoryState): HistoryState {
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
    rotation: settings.rotation,
    brightness: settings.brightness,
    contrast: settings.contrast,
    saturation: settings.saturation,
    temperature: settings.temperature,
    filter: settings.filter,
    texts: settings.texts.map((t) => ({ ...t })),
  };
}

export function clampSlider(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
