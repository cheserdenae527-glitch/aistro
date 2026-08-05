// 直播工坊编辑器测试 — 定稿/导出禁用逻辑 / regenerate 二次确认 / 开播前置校验 / 补录必填
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LiveScript, LiveSession } from "../services/live";
import { liveService } from "../services/live";
import { shopService } from "../services/shops";
import LiveEditorPage from "./LiveEditorPage";

vi.mock("../services/live", () => ({
  liveService: {
    getProject: vi.fn(),
    listScripts: vi.fn(),
    listAvatars: vi.fn(),
    updateProject: vi.fn(),
    engineTest: vi.fn(),
    generateScript: vi.fn(),
    updateScript: vi.fn(),
    confirmScript: vi.fn(),
    exportScript: vi.fn(),
    complianceCheck: vi.fn(),
    getDanmaku: vi.fn(),
    generateDanmaku: vi.fn(),
    updateDanmaku: vi.fn(),
    listSessions: vi.fn(),
    createSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    getMetrics: vi.fn(),
    upsertMetrics: vi.fn(),
    reviewSession: vi.fn(),
  },
}));

vi.mock("../services/shops", () => ({
  shopService: { get: vi.fn() },
}));

vi.mock("../store/auth", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { id: "user-1", name: "测试运营" } }),
}));

const project = {
  id: "proj-1",
  shop_id: "shop-1",
  title: "火锅直播间",
  platform: "douyin",
  goal: "提升核销",
  promo_items: null,
  ai_label_text: "本直播间由 AI 数字人出镜，真人运营团队值守",
  engine_config: null,
  status: "active",
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
};

const shop = {
  id: "shop-1",
  merchant_id: "m1",
  name: "测试火锅店",
  address: null,
  phone: null,
  category: "火锅",
  status: "active",
  created_at: "2026-08-05T00:00:00Z",
};

const avatar = {
  id: "a1",
  org_id: "user-1",
  name: "店长小雅",
  avatar_type: "image",
  image_url: null,
  video_url: null,
  voice_config: null,
  persona: { identity: "店长小雅", tone: "亲切" },
  status: "ready",
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
};

function script(over: Partial<LiveScript> = {}): LiveScript {
  return {
    id: "s1",
    project_id: "proj-1",
    avatar_id: "a1",
    persona_snapshot: { identity: "店长小雅", tone: "亲切" },
    generation_batch: 1,
    title: "招牌直播脚本",
    tone: "烟火气",
    content: [
      { type: "opening", title: "开场留人", text: "欢迎来到直播间", duration_sec: 60, cue: null },
      { type: "closing", title: "收尾", text: "记得核销", duration_sec: 60, cue: null },
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

function session(over: Partial<LiveSession> = {}): LiveSession {
  return {
    id: "ss1",
    project_id: "proj-1",
    script_id: null,
    avatar_id: null,
    scheduled_at: "2026-08-10T20:00:00+08:00",
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
    ...over,
  };
}

const bundle = {
  script_markdown: "# 招牌直播脚本\n## 开场留人（60s）\n欢迎来到直播间",
  persona_json: { identity: "店长小雅" },
  wordlist: ["加微信"],
  reply_rules: [{ trigger: "优惠", reply: "9.9 元起", mode: "manual" }],
  compliance: { pass: true, items: [] },
  engine_guide: "启动 LiveTalking…",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/live/proj-1"]}>
      <Routes>
        <Route path="/live/:id" element={<LiveEditorPage />} />
      </Routes>
    </MemoryRouter>
  );
}

async function openScriptTab() {
  await screen.findByText("火锅直播间");
  await userEvent.click(screen.getByRole("tab", { name: "直播脚本" }));
}

async function openSessionsTab() {
  await screen.findByText("火锅直播间");
  await userEvent.click(screen.getByRole("tab", { name: "场次与复盘" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  (liveService.getProject as ReturnType<typeof vi.fn>).mockResolvedValue({ data: project });
  (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
  (liveService.listAvatars as ReturnType<typeof vi.fn>).mockResolvedValue({
    data: { items: [avatar], total: 1, page: 1, size: 20 },
  });
  (liveService.getDanmaku as ReturnType<typeof vi.fn>).mockRejectedValue({ response: { status: 404 } });
  (liveService.getMetrics as ReturnType<typeof vi.fn>).mockRejectedValue({ response: { status: 404 } });
});

describe("LiveEditorPage · 直播脚本", () => {
  it("草稿脚本：导出禁用，定稿可用；合规失败后定稿禁用并展示原因", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [script()] });
    (liveService.complianceCheck as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { pass: false, items: [{ key: "ai_label", ok: false, detail: "未配置 AI 标识文案" }] },
    });

    await renderPage();
    await openScriptTab();

    const exportBtn = screen.getByRole("button", { name: /导出开播包/ });
    expect(exportBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: /定\s*稿/ })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: /合规自检/ }));
    expect((await screen.findAllByText("未配置 AI 标识文案")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /定\s*稿/ })).toBeDisabled();
  });

  it("定稿成功 → 导出可用并弹出开播包", async () => {
    const confirmed = script({ status: "confirmed", compliance: { pass: true, items: [] } });
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [script()] });
    (liveService.confirmScript as ReturnType<typeof vi.fn>).mockResolvedValue({ data: confirmed });
    (liveService.exportScript as ReturnType<typeof vi.fn>).mockResolvedValue({ data: bundle });

    await renderPage();
    await openScriptTab();
    await userEvent.click(screen.getByRole("button", { name: /定\s*稿/ }));

    const exportBtn = await screen.findByRole("button", { name: /导出开播包/ });
    await waitFor(() => expect(exportBtn).toBeEnabled());

    await userEvent.click(exportBtn);
    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByText(/欢迎来到直播间/)).toBeInTheDocument();
  });

  it("已归档脚本（无活跃批次）：导出禁用", async () => {
    const archived = script({ id: "s9", status: "confirmed", is_archived: true });
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [archived] });

    await renderPage();
    await openScriptTab();
    expect(screen.getByRole("button", { name: /导出开播包/ })).toBeDisabled();
  });

  it("已有活跃批次 → 生成脚本二次确认「归档」→ 生成表单 → 调用生成", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [script()] });
    (liveService.generateScript as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: script({ id: "s2", generation_batch: 2 }),
    });
    let captured: { onOk?: () => void } = {};
    const confirmSpy = vi.spyOn(Modal, "confirm").mockImplementation((config) => {
      captured = config as { onOk?: () => void };
      return { destroy: vi.fn() } as never;
    });

    await renderPage();
    await openScriptTab();
    await userEvent.click(screen.getByRole("button", { name: /生成脚本/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(captured)).toContain("归档");

    await act(async () => {
      await captured.onOk?.();
    });
    await screen.findByText("生成直播脚本");
    await userEvent.click(screen.getByRole("button", { name: /开始生成/ }));
    await waitFor(() =>
      expect(liveService.generateScript).toHaveBeenCalledWith("proj-1", {
        avatar_id: "a1",
        tone: "烟火气",
        duration_min: 2,
      })
    );
  });
});

describe("LiveEditorPage · 场次与复盘", () => {
  it("开播前置校验：未确认值守/AI 标识 → 拦截不调接口；确认后调用状态流转", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [session()], total: 1, page: 1, size: 20 },
    });
    (liveService.updateSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: session({ status: "live", duty_confirmed: true, ai_label_confirmed: true }),
    });

    await renderPage();
    await openSessionsTab();
    await screen.findByText("待开播");

    await userEvent.click(screen.getByRole("button", { name: /开播/ }));
    await screen.findByText("开播前置确认");
    await userEvent.click(screen.getByRole("button", { name: /确认开播/ }));
    expect(liveService.updateSession).not.toHaveBeenCalled();

    // 打开两个确认开关（值守 + AI 标识）
    const switches = screen.getAllByRole("switch");
    await userEvent.click(switches[0]);
    await userEvent.click(switches[1]);
    await userEvent.click(screen.getByRole("button", { name: /确认开播/ }));
    await waitFor(() =>
      expect(liveService.updateSession).toHaveBeenCalledWith("proj-1", "ss1", {
        operator_id: "user-1",
        duty_confirmed: true,
        ai_label_confirmed: true,
        status: "live",
      })
    );
  });

  it("补录必填校验：缺开始/结束时间 → 不调接口", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [session()], total: 1, page: 1, size: 20 },
    });

    await renderPage();
    await openSessionsTab();
    await screen.findByText("待开播");

    await userEvent.click(screen.getByRole("button", { name: /补\s*录/ }));
    await screen.findByText("补录已完成场次");
    await userEvent.click(screen.getByRole("button", { name: /保存补录/ }));

    await screen.findByText("必填");
    expect(liveService.updateSession).not.toHaveBeenCalled();
  });
});


describe("LiveEditorPage · 本地引擎连接测试", () => {
  it("未配置 base_url 时连接测试按钮禁用，不调用接口", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    await renderPage();
    await screen.findByText("火锅直播间");
    expect(screen.getByRole("button", { name: /连接测试/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /连接测试/ }));
    expect(liveService.engineTest).not.toHaveBeenCalled();
  });

  it("已有最近健康检查时间时在基本信息展示", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.getProject as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        ...project,
        engine_config: {
          base_url: "http://localhost:8010",
          enabled: true,
          api_key_configured: true,
          last_health_check: "2026-08-05T04:00:00+00:00",
        },
      },
    });
    await renderPage();
    await screen.findByText("火锅直播间");
    expect(screen.getByText(/最近健康检查/)).toBeInTheDocument();
    expect(screen.getByText(/引擎启用/)).toBeInTheDocument();
  });

  it("清空已保存 base_url 后点击 → 不调用接口", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.getProject as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        ...project,
        engine_config: { base_url: "http://localhost:8010", enabled: true, api_key_configured: true },
      },
    });
    await renderPage();
    await screen.findByText("火锅直播间");
    const input = screen.getByPlaceholderText("http://localhost:8010");
    await userEvent.clear(input);
    await userEvent.click(screen.getByRole("button", { name: /连接测试/ }));
    expect(liveService.engineTest).not.toHaveBeenCalled();
  });

  it("填写 base_url → 连接测试调用 engineTest 并展示报告", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.engineTest as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        ok: true,
        base_url: "http://localhost:8010",
        health: { ok: true, status_code: 200, latency_ms: 12, detail: "ok" },
        persona_push: { status: "ok", detail: "ok" },
        wordlist_push: { status: "skipped", detail: "纯 LiveTalking" },
        last_health_check: "2026-08-05T03:00:00+00:00",
        error: null,
      },
    });

    await renderPage();
    await screen.findByText("火锅直播间");
    const input = screen.getByPlaceholderText("http://localhost:8010");
    await userEvent.type(input, "http://localhost:8010");
    await userEvent.click(screen.getByRole("button", { name: /连接测试/ }));

    await waitFor(() =>
      expect(liveService.engineTest).toHaveBeenCalledWith("proj-1", {
        base_url: "http://localhost:8010",
      })
    );
    expect(await screen.findByText(/健康检查：通过/)).toBeInTheDocument();
    expect(screen.getByText(/人设推送：已推送/)).toBeInTheDocument();
    expect(screen.getByText(/敏感词推送：已跳过/)).toBeInTheDocument();
  });

  it("接口失败（502）→ 展示错误且不展示报告", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.engineTest as ReturnType<typeof vi.fn>).mockRejectedValue({
      response: { status: 502, data: { detail: "引擎健康检查失败：无法连接" } },
    });

    await renderPage();
    await screen.findByText("火锅直播间");
    const input = screen.getByPlaceholderText("http://localhost:8010");
    await userEvent.type(input, "http://localhost:8010");
    await userEvent.click(screen.getByRole("button", { name: /连接测试/ }));

    await waitFor(() => expect(liveService.engineTest).toHaveBeenCalled());
    expect(await screen.findByText(/引擎健康检查失败/)).toBeInTheDocument();
    expect(screen.queryByText(/健康检查：通过/)).not.toBeInTheDocument();
  });
});


describe("LiveEditorPage · 引擎画面预览", () => {
  it("引擎启用时场次 Tab 展示画面预览 iframe", async () => {
    (liveService.listScripts as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (liveService.listSessions as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20 },
    });
    (liveService.getProject as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        ...project,
        engine_config: {
          base_url: "http://localhost:8010",
          enabled: true,
          api_key_configured: true,
        },
      },
    });
    await renderPage();
    await screen.findByText("火锅直播间");
    await userEvent.click(screen.getByRole("tab", { name: "场次与复盘" }));
    expect(await screen.findByText("引擎画面预览（本地数字人）")).toBeInTheDocument();
    expect(screen.getByText(/预览高度/)).toBeInTheDocument();
    expect(screen.getByText(/3:4 竖版/)).toBeInTheDocument();
  });
});

