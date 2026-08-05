import { describe, expect, it } from "vitest";
import {
  categoryCount,
  countdownText,
  formatDensity,
  formatDistance,
  formatTime,
  hasMapData,
  remainingCooldown,
  sortCategoryStats,
} from "./district";
import type { SnapshotSummary } from "../services/district";

describe("formatDensity", () => {
  it("正常值保留两位小数", () => {
    expect(formatDensity(1.486)).toBe("1.49 家/km²");
  });
  it("null / undefined / NaN 返回占位符", () => {
    expect(formatDensity(null)).toBe("—");
    expect(formatDensity(undefined)).toBe("—");
    expect(formatDensity(Number.NaN)).toBe("—");
  });
});

describe("categoryCount / sortCategoryStats", () => {
  const stats = [
    { category: "火锅店", count: 8 },
    { category: "奶茶店", count: 3 },
    { category: "快餐", count: 5 },
  ];
  it("品类数统计", () => {
    expect(categoryCount(stats)).toBe(3);
    expect(categoryCount(null)).toBe(0);
    expect(categoryCount(undefined)).toBe(0);
  });
  it("按数量降序且不修改入参", () => {
    const sorted = sortCategoryStats(stats);
    expect(sorted.map((s) => s.count)).toEqual([8, 5, 3]);
    expect(stats[0].count).toBe(8); // 原数组未被改动
  });
  it("空输入返回空数组", () => {
    expect(sortCategoryStats(null)).toEqual([]);
  });
});

describe("formatDistance", () => {
  it("小于 1km 用米", () => {
    expect(formatDistance(300)).toBe("300m");
    expect(formatDistance(999)).toBe("999m");
  });
  it("≥1km 用公里", () => {
    expect(formatDistance(1500)).toBe("1.5km");
    expect(formatDistance(6351)).toBe("6.4km");
  });
  it("null 返回占位符", () => {
    expect(formatDistance(null)).toBe("—");
  });
});

describe("formatTime", () => {
  it("格式化 ISO 时间", () => {
    // 本地时区无关断言：直接构造本地时间字符串
    const d = new Date(2026, 7, 4, 9, 5);
    expect(formatTime(d.toISOString())).toContain("2026-08-04");
  });
  it("空值返回占位符", () => {
    expect(formatTime(null)).toBe("—");
    expect(formatTime("not-a-date")).toBe("—");
  });
});

describe("hasMapData", () => {
  const base: SnapshotSummary = {
    id: "s1",
    shop_id: "sh1",
    center_lng: 114.29,
    center_lat: 30.58,
    geocode_level: "门牌号",
    radius_m: 3000,
    poi_total: 10,
    competitor_count: 2,
    category_stats: [],
    density_per_km2: 1.2,
    mapping_status: "full",
    status: "analyzed",
    error_message: null,
    excluded_self_count: 0,
    created_at: "2026-08-04T00:00:00Z",
  };
  it("analyzed 且含坐标 → true", () => {
    expect(hasMapData(base)).toBe(true);
  });
  it("failed 或坐标缺失 → false", () => {
    expect(hasMapData({ ...base, status: "failed" })).toBe(false);
    expect(hasMapData({ ...base, center_lng: null })).toBe(false);
    expect(hasMapData(null)).toBe(false);
  });
});

describe("countdown", () => {
  it("countdownText 分:秒格式", () => {
    expect(countdownText(60)).toBe("1:00");
    expect(countdownText(5)).toBe("0:05");
    expect(countdownText(0)).toBe("0:00");
    expect(countdownText(-3)).toBe("0:00");
  });
  it("remainingCooldown 不为负", () => {
    expect(remainingCooldown(60, 12)).toBe(48);
    expect(remainingCooldown(60, 99)).toBe(0);
  });
});
