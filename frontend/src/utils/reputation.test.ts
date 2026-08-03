import { describe, expect, it } from "vitest";

import {
  buildReviewParams,
  MAX_BATCH_ANALYZE,
  replyStatusMeta,
  toggleSelection,
} from "./reputation";

describe("buildReviewParams", () => {
  it("只携带已设置的筛选条件与分页", () => {
    const params = buildReviewParams(
      {
        review_type: "comment",
        sentiment: "negative",
        reply_status: "unreplied",
        alert_status: "triggered",
        keyword: "分量少",
        parent_review_id: "note-1",
        date_from: "2026-08-01T00:00:00Z",
        date_to: "2026-08-03T23:59:59Z",
      },
      2,
      50
    );
    expect(params).toEqual({
      review_type: "comment",
      sentiment: "negative",
      reply_status: "unreplied",
      alert_status: "triggered",
      keyword: "分量少",
      parent_review_id: "note-1",
      date_from: "2026-08-01T00:00:00Z",
      date_to: "2026-08-03T23:59:59Z",
      page: 2,
      size: 50,
    });
  });

  it("空筛选只返回分页参数", () => {
    expect(buildReviewParams({}, 1, 20)).toEqual({ page: 1, size: 20 });
  });
});

describe("toggleSelection", () => {
  it("勾选上限为 20，超限拒绝", () => {
    const ids = Array.from({ length: MAX_BATCH_ANALYZE }, (_, i) => `id-${i}`);
    const result = toggleSelection(ids, "id-20");
    expect(result.rejected).toBe(true);
    expect(result.ids).toHaveLength(MAX_BATCH_ANALYZE);
  });

  it("取消勾选与正常新增", () => {
    const added = toggleSelection(["a"], "b");
    expect(added).toEqual({ ids: ["a", "b"], rejected: false });
    const removed = toggleSelection(["a", "b"], "a");
    expect(removed).toEqual({ ids: ["b"], rejected: false });
  });
});

describe("replyStatusMeta", () => {
  it("映射回复状态文案与颜色", () => {
    expect(replyStatusMeta("unreplied")).toEqual({ label: "未回复", color: "default" });
    expect(replyStatusMeta("ai_replied")).toEqual({ label: "AI 草稿", color: "blue" });
    expect(replyStatusMeta("manual_replied")).toEqual({ label: "已回复", color: "green" });
    expect(replyStatusMeta(null)).toEqual({ label: "无需回复", color: "default" });
  });
});
