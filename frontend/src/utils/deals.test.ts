import { describe, expect, it } from "vitest";
import type { DealScheme, DealSchemeCopy } from "../services/deals";
import {
  buildCopyClipboardText,
  copyForPlatform,
  formatPrice,
  marginLines,
  percent,
  shouldConfirmRegenerate,
} from "./deals";

const copy: DealSchemeCopy = {
  id: "c1",
  scheme_id: "s1",
  platform: "douyin",
  title: "9.9吃招牌！现炒火锅单人餐",
  selling_points: ["现炒底料", "30分钟出餐"],
  rules: "仅限周一至周五午餐，每桌限用1份",
  cover_prompt: "cover",
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
};

const scheme: DealScheme = {
  id: "s1",
  project_id: "p1",
  scheme_type: "profit",
  generation_batch: 1,
  title: "利润款",
  description: null,
  items: [],
  original_price: "126.00",
  deal_price: "88.00",
  cost_estimate: "45.00",
  margin_estimate: {
    gross_margin: 0.4886,
    platform_commission_rate: 0.06,
    net_margin: 0.4286,
    note: "",
  },
  status: "draft",
  is_archived: false,
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
  copies: [copy],
};

describe("percent / formatPrice", () => {
  it("百分比格式化", () => {
    expect(percent(0.4886)).toBe("48.9%");
    expect(percent(-0.1)).toBe("-10.0%");
    expect(percent(0)).toBe("0.0%");
    expect(percent(null)).toBe("-");
    expect(percent(undefined)).toBe("-");
    expect(percent(Number.NaN)).toBe("-");
  });

  it("价格格式化", () => {
    expect(formatPrice("88.00")).toBe("¥88.00");
    expect(formatPrice(88)).toBe("¥88.00");
    expect(formatPrice(null)).toBe("-");
    expect(formatPrice(undefined)).toBe("-");
    expect(formatPrice("abc")).toBe("-");
  });
});

describe("marginLines", () => {
  it("毛利两行 + 佣金率 + note", () => {
    expect(
      marginLines({
        gross_margin: 0.4886,
        platform_commission_rate: 0.06,
        net_margin: 0.4286,
        note: "含 AI 估算成本",
      })
    ).toEqual({
      gross: "48.9%",
      net: "42.9%",
      rate: "6.0%",
      note: "含 AI 估算成本",
    });
  });

  it("无毛利数据时全部占位", () => {
    expect(marginLines(null)).toEqual({ gross: "-", net: "-", rate: "-", note: "" });
  });
});

describe("shouldConfirmRegenerate", () => {
  it("无方案时不需要确认", () => {
    expect(shouldConfirmRegenerate([])).toBe(false);
  });

  it("存在未归档方案时需要确认", () => {
    expect(shouldConfirmRegenerate([scheme])).toBe(true);
  });

  it("仅存在归档方案时不需要确认", () => {
    expect(shouldConfirmRegenerate([{ ...scheme, is_archived: true }])).toBe(false);
  });
});

describe("copyForPlatform / buildCopyClipboardText", () => {
  it("按平台取文案", () => {
    expect(copyForPlatform(scheme, "douyin")?.id).toBe("c1");
    expect(copyForPlatform(scheme, "meituan")).toBeUndefined();
  });

  it("组装复制文本（标题 + 卖点 + 规则）", () => {
    const text = buildCopyClipboardText(copy);
    expect(text).toContain("9.9吃招牌！现炒火锅单人餐");
    expect(text).toContain("- 现炒底料");
    expect(text).toContain("仅限周一至周五午餐");
  });

  it("无文案时返回空串", () => {
    expect(buildCopyClipboardText(undefined)).toBe("");
  });
});
