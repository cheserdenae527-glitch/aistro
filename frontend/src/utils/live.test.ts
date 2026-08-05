import { describe, expect, it } from "vitest";
import type { LiveScript, LiveSession } from "../services/live";
import {
  activeScript,
  canExport,
  complianceFailures,
  formatDateTime,
  formatDuration,
  formatDurationShort,
  isConfirmed,
  isTerminal,
  latestScript,
  scriptSegments,
  sessionScriptLabel,
  shouldConfirmRegenerate,
  totalDuration,
} from "./live";

function script(over: Partial<LiveScript> = {}): LiveScript {
  return {
    id: "s1",
    project_id: "p1",
    avatar_id: "a1",
    persona_snapshot: null,
    generation_batch: 1,
    title: "脚本",
    tone: "烟火气",
    content: [
      { type: "opening", title: "开场", text: "欢迎", duration_sec: 60, cue: null },
      { type: "closing", title: "收尾", text: "再见", duration_sec: 60, cue: null },
    ],
    total_duration_sec: 120,
    status: "draft",
    is_archived: false,
    compliance: null,
    created_at: "2026-08-05T00:00:00Z",
    updated_at: "2026-08-05T00:00:00Z",
    ...over,
  };
}

describe("live utils", () => {
  it("formatDuration 分段/分钟/小时", () => {
    expect(formatDuration(45)).toBe("45 秒");
    expect(formatDuration(120)).toBe("2 分钟");
    expect(formatDuration(150)).toBe("2 分 30 秒");
    expect(formatDuration(3660)).toBe("1 小时 1 分");
    expect(formatDuration(null)).toBe("-");
    expect(formatDurationShort(90)).toBe("90s");
  });

  it("formatDateTime 本地时间", () => {
    const s = formatDateTime("2026-08-10T20:00:00+08:00");
    expect(s).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(formatDateTime(null)).toBe("-");
  });

  it("activeScript / latestScript 按批次取最新", () => {
    const s1 = script({ id: "s1", generation_batch: 1 });
    const s2 = script({ id: "s2", generation_batch: 2 });
    const s3 = script({ id: "s3", generation_batch: 3, is_archived: true });
    expect(activeScript([s1, s2])?.id).toBe("s2");
    expect(activeScript([s3, s1])?.id).toBe("s1");
    expect(activeScript([])).toBeNull();
    expect(latestScript([s1, s3, s2])?.id).toBe("s3");
  });

  it("shouldConfirmRegenerate 已有活跃批次或已定稿 → true", () => {
    expect(shouldConfirmRegenerate([script()])).toBe(true);
    expect(
      shouldConfirmRegenerate([script({ is_archived: true, status: "confirmed" })])
    ).toBe(true);
    expect(
      shouldConfirmRegenerate([script({ is_archived: true, status: "draft" })])
    ).toBe(false);
    expect(shouldConfirmRegenerate([])).toBe(false);
  });

  it("canExport 仅活跃批次 confirmed", () => {
    expect(canExport(script({ status: "confirmed" }))).toBe(true);
    expect(canExport(script({ status: "draft" }))).toBe(false);
    expect(canExport(script({ status: "confirmed", is_archived: true }))).toBe(false);
    expect(canExport(null)).toBe(false);
    expect(isConfirmed(script({ status: "confirmed", is_archived: true }))).toBe(true);
  });

  it("complianceFailures / totalDuration / scriptSegments", () => {
    expect(
      complianceFailures([
        { key: "a", ok: true, detail: "ok" },
        { key: "b", ok: false, detail: "bad" },
      ])
    ).toHaveLength(1);
    expect(complianceFailures(null)).toHaveLength(0);
    expect(totalDuration(script())).toBe(120);
    expect(scriptSegments(null)).toHaveLength(0);
  });

  it("isTerminal / sessionScriptLabel", () => {
    expect(isTerminal("ended")).toBe(true);
    expect(isTerminal("cancelled")).toBe(true);
    expect(isTerminal("live")).toBe(false);
    const session: LiveSession = {
      id: "ss1",
      project_id: "p1",
      script_id: "s2",
      avatar_id: null,
      scheduled_at: "2026-08-10T20:00:00Z",
      duration_min: 60,
      status: "planned",
      operator_id: null,
      duty_confirmed: false,
      ai_label_confirmed: false,
      is_backfilled: false,
      notes: null,
      started_at: null,
      ended_at: null,
      created_at: "2026-08-05T00:00:00Z",
      updated_at: "2026-08-05T00:00:00Z",
    };
    expect(sessionScriptLabel(session, [script({ id: "s2", title: "夏季脚本" })])).toBe("夏季脚本");
    expect(sessionScriptLabel({ ...session, script_id: null }, [])).toBe("纯人工直播（无脚本）");
  });
});
