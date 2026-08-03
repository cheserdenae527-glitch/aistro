import { describe, expect, it } from "vitest";
import {
  commit,
  createHistory,
  DEFAULT_SETTINGS,
  redo,
  replace,
  serializeSettings,
  undo,
} from "./editStack";

describe("editStack undo/redo", () => {
  it("commits push present to past and clear future", () => {
    const state = createHistory();
    const next = commit(state, { ...DEFAULT_SETTINGS, brightness: 120 });

    expect(next.past).toEqual([DEFAULT_SETTINGS]);
    expect(next.present.brightness).toBe(120);
    expect(next.future).toEqual([]);
  });

  it("undo and redo restore states in order", () => {
    let state = createHistory();
    state = commit(state, { ...state.present, brightness: 110 });
    state = commit(state, { ...state.present, contrast: 130 });

    const undone1 = undo(state);
    expect(undone1.present.brightness).toBe(110);
    expect(undone1.present.contrast).toBe(100);

    const undone2 = undo(undone1);
    expect(undone2.present).toEqual(DEFAULT_SETTINGS);
    expect(undo(undone2)).toEqual(undone2);

    const redone1 = redo(undone2);
    expect(redone1.present.brightness).toBe(110);
    const redone2 = redo(redone1);
    expect(redone2.present.contrast).toBe(130);
    expect(redo(redone2)).toEqual(redone2);
  });

  it("replace during slider drag does not create history nodes", () => {
    let state = createHistory();
    state = replace(state, { ...state.present, brightness: 115 });
    state = replace(state, { ...state.present, brightness: 120 });

    expect(state.past).toEqual([]);
    expect(state.present.brightness).toBe(120);
    expect(state.future).toEqual([]);

    const committed = commit(state, { ...state.present, saturation: 80 });
    expect(committed.past).toEqual([state.present]);
  });
});

describe("slider params serialization", () => {
  it("serializes only whitelisted edit_stack fields", () => {
    const state = createHistory({
      ...DEFAULT_SETTINGS,
      crop: { x: 10, y: 20, w: 300, h: 200 },
      rotation: 90,
      brightness: 110,
      contrast: 95,
      saturation: 120,
      temperature: 15,
      filter: "warm",
      texts: [
        {
          id: "t1",
          text: "招牌必点",
          x: 0.5,
          y: 0.4,
          size: 5,
          color: "#FFFFFF",
        },
      ],
    });

    const serialized = serializeSettings(state.present);
    expect(Object.keys(serialized).sort()).toEqual([
      "brightness",
      "contrast",
      "crop",
      "filter",
      "rotation",
      "saturation",
      "temperature",
      "texts",
    ]);
    expect(JSON.parse(JSON.stringify(serialized))).toMatchObject({
      crop: { x: 10, y: 20, w: 300, h: 200 },
      rotation: 90,
      brightness: 110,
      filter: "warm",
      texts: [{ id: "t1", text: "招牌必点", x: 0.5, y: 0.4, size: 5, color: "#FFFFFF" }],
    });
  });

  it("default settings serialize without NaN or missing fields", () => {
    const serialized = serializeSettings(DEFAULT_SETTINGS);
    expect(serialized.brightness).toBe(100);
    expect(serialized.texts).toEqual([]);
    expect(serialized.crop).toBeNull();
  });
});
