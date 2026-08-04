import { describe, expect, it } from "vitest";
import {
  addWithCap,
  candidateToAsset,
  clampPageCount,
  EDITORIAL_THEMES,
  isCopyUsable,
  qaSummary,
  SWISS_THEMES,
  themeOptions,
  toggleSelection,
  validateCopyForm,
} from "./studio";
import type { QaReport, StudioCopy } from "../services/studio";

describe("validateCopyForm", () => {
  it("空表单返回全部必填错误", () => {
    const errors = validateCopyForm({
      category: "",
      style: "",
      price_range: "",
      topic: "",
      shop_name: "",
    });
    expect(errors.length).toBe(5);
  });

  it("只填部分字段时只报缺失项", () => {
    const errors = validateCopyForm({
      category: "市井火锅",
      style: "烟火气",
      price_range: "人均80",
      topic: "",
      shop_name: "",
    });
    expect(errors).toEqual(["主题不能为空", "店名不能为空"]);
  });

  it("全部填写后无错误", () => {
    const errors = validateCopyForm({
      category: "市井火锅",
      style: "烟火气",
      price_range: "人均80",
      topic: "宝藏火锅",
      shop_name: "蜀香里火锅",
    });
    expect(errors).toEqual([]);
  });
});

describe("clampPageCount", () => {
  it("页数限制在 4-8", () => {
    expect(clampPageCount(3)).toBe(4);
    expect(clampPageCount(9)).toBe(8);
    expect(clampPageCount(6)).toBe(6);
  });

  it("四舍五入并处理 NaN", () => {
    expect(clampPageCount(5.6)).toBe(6);
    expect(clampPageCount(Number.NaN)).toBe(4);
  });
});

describe("isCopyUsable", () => {
  it("文案需含标题和正文", () => {
    expect(
      isCopyUsable({ titles: [{ text: "t", strategy: "s" }], body: "正文" } as unknown as StudioCopy)
    ).toBe(true);
    expect(isCopyUsable({ titles: [], body: "正文" } as unknown as StudioCopy)).toBe(false);
    expect(isCopyUsable(null)).toBe(false);
    expect(isCopyUsable({ titles: [{ text: "t", strategy: "s" }], body: "" } as unknown as StudioCopy)).toBe(
      false
    );
  });
});

describe("qaSummary", () => {
  const qa: QaReport = {
    all_pass: true,
    pages: [
      {
        page: 1,
        pass: true,
        checks: {
          density: { pass: true, coverage: 90, bands: [90], issues: [] },
          overflow: { pass: true, overflow_px: 0 },
          bottom_blank: { pass: true, bottom_gap_px: 100 },
        },
        issues: [],
      },
      { page: 2, pass: true, checks: {} as never, issues: [] },
    ],
  };

  it("统计通过页数", () => {
    expect(qaSummary(qa)).toEqual({ allPass: true, passCount: 2, total: 2 });
  });

  it("null 或空返回 0", () => {
    expect(qaSummary(null)).toEqual({ allPass: false, passCount: 0, total: 0 });
    expect(qaSummary({ all_pass: false, pages: [] })).toEqual({
      allPass: false,
      passCount: 0,
      total: 0,
    });
  });
});

describe("themeOptions", () => {
  it("Editorial 6 套 / Swiss 4 套", () => {
    expect(EDITORIAL_THEMES).toHaveLength(6);
    expect(SWISS_THEMES).toHaveLength(4);
    expect(themeOptions("editorial")).toHaveLength(6);
    expect(themeOptions("swiss")).toHaveLength(4);
  });

  it("主题 key 唯一", () => {
    const keys = [...EDITORIAL_THEMES, ...SWISS_THEMES].map((t) => t.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("toggleSelection", () => {
  it("选中 / 取消选中", () => {
    const r1 = toggleSelection(["a"], "b", (x, y) => x === y, 8);
    expect(r1).toEqual({ items: ["a", "b"], added: true });
    const r2 = toggleSelection(["a", "b"], "a", (x, y) => x === y, 8);
    expect(r2).toEqual({ items: ["b"], added: false });
  });

  it("达到上限后不再新增", () => {
    const r = toggleSelection(["a", "b"], "c", (x, y) => x === y, 2);
    expect(r).toEqual({ items: ["a", "b"], added: false });
  });
});

describe("addWithCap", () => {
  it("截取到上限并返回溢出数量", () => {
    const r = addWithCap(["a"], ["b", "c", "d"], 3);
    expect(r.items).toEqual(["a", "b", "c"]);
    expect(r.overflow).toBe(1);
  });

  it("未超限时全部加入", () => {
    const r = addWithCap(["a"], ["b"], 3);
    expect(r.items).toEqual(["a", "b"]);
    expect(r.overflow).toBe(0);
  });
});
describe("candidateToAsset", () => {
  it("把 AI 候选转换为可引用素材（pending/ai/photo）", () => {
    const asset = candidateToAsset(
      { aid: "a1", url: "https://cdn/x.png", thumb_url: "https://cdn/x_thumb.png", batch_id: "b1" },
      "proj-1"
    );
    expect(asset.id).toBe("a1");
    expect(asset.project_id).toBe("proj-1");
    expect(asset.source).toBe("ai");
    expect(asset.status).toBe("pending");
    expect(asset.asset_type).toBe("photo");
    expect(asset.batch_id).toBe("b1");
    expect(asset.thumb_url).toBe("https://cdn/x_thumb.png");
  });
});
