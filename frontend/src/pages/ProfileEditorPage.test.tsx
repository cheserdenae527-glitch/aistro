// 店铺装修编辑器测试 — 加载 / AI 建议 / 按建议优化 / 保存草稿 / 复制拦截
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ShopProfile } from "../services/profiles";
import { profileService } from "../services/profiles";
import ProfileEditorPage from "./ProfileEditorPage";

vi.mock("../services/profiles", () => ({
  profileService: {
    analyzeStyle: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    generate: vi.fn(),
    generatePrompt: vi.fn(),
    healthCheck: vi.fn(),
    generatePinnedNotes: vi.fn(),
    rewriteByHealthCheck: vi.fn(),
    generateProfileOptions: vi.fn(),
    createImageJob: vi.fn(),
    createImageJobWithRef: vi.fn(),
    getImageJob: vi.fn(),
    selectAvatar: vi.fn(),
    selectBgImage: vi.fn(),
    removeGalleryImage: vi.fn(),
    uploadAvatar: vi.fn(),
    uploadBgImage: vi.fn(),
    cropAvatar: vi.fn(),
    cropBgImage: vi.fn(),
    getColorSchemes: vi.fn(),
    getHistory: vi.fn(),
    restoreHistory: vi.fn(),
  },
}));

const mocked = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const defaultProfile = (overrides: Partial<ShopProfile> = {}): ShopProfile => ({
  id: "p1",
  shop_id: "shop-1",
  platform: "xiaohongshu",
  nickname: "巷子口老灶火锅",
  bio: "人均80吃撑",
  avatar_url: null,
  avatar_original_url: null,
  avatar_gen_prompt: "红铜锅头像",
  avatar_options: [],
  bg_image_url: null,
  bg_original_url: null,
  bg_gen_prompt: "老巷子背景",
  bg_options: [],
  color_primary: "#C93828",
  color_secondary: "#FFF0EE",
  color_accent: "#A82015",
  color_text: "#2A0A08",
  color_mode: "preset",
  color_preset_name: "江湖红",
  ai_variants: null,
  health_check: null,
  pinned_notes: [],
  bio_flagged: false,
  status: "draft",
  version: 3,
  ...overrides,
});

const healthResult = {
  first_impression: "一眼看出是火锅店",
  strengths: ["人均价格具体"],
  weaknesses: ["目标用户不清晰"],
  suggestions: ["写明目标人群"],
  checked_at: "2026-08-06T00:00:00Z",
  snapshot: {
    nickname: "巷子口老灶火锅",
    bio: "人均80吃撑",
    avatar_prompt: "红铜锅头像",
    bg_prompt: "老巷子背景",
    pinned_notes: [],
    color_primary: "#C93828",
    color_secondary: "#FFF0EE",
    color_accent: "#A82015",
    color_text: "#2A0A08",
    has_avatar: false,
    has_bg: false,
  },
};

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/shops/shop-1/profile/xiaohongshu"]}>
      <Routes>
        <Route
          path="/shops/:shop_id/profile/:platform"
          element={<ProfileEditorPage />}
        />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
  mocked(profileService.get).mockResolvedValue({ data: defaultProfile() });
  mocked(profileService.getColorSchemes).mockResolvedValue({ data: [] });
  mocked(profileService.update).mockResolvedValue({ data: defaultProfile() });
  mocked(profileService.getHistory).mockResolvedValue({ data: [] });
});

describe("ProfileEditorPage", () => {
  it("加载草稿并展示核心功能区", async () => {
    mocked(profileService.get).mockResolvedValue({
      data: defaultProfile({
        pinned_notes: [{ title: "怎么找到我们", content: "评论区扣1" }],
        health_check: healthResult,
      }),
    });

    renderPage();

    expect(await screen.findByDisplayValue("巷子口老灶火锅")).toBeInTheDocument();
    expect(screen.getByText("置顶笔记")).toBeInTheDocument();
    expect(screen.getByDisplayValue("怎么找到我们")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /AI 建议/ })).toHaveLength(2);
    expect(screen.getByRole("button", { name: /按建议优化/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /历史版本/ })).toBeInTheDocument();
    expect(screen.getByText("一眼看出是火锅店")).toBeInTheDocument();
  });

  it("AI 建议生成昵称候选并可点选填入", async () => {
    mocked(profileService.generateProfileOptions).mockResolvedValue({
      data: { options: ["巷子口·本地回头客"] },
    });

    renderPage();
    await screen.findByDisplayValue("巷子口老灶火锅");

    const nicknameCard = screen.getByText("昵称").closest(".ant-card") as HTMLElement;
    await userEvent.click(within(nicknameCard).getByRole("button", { name: /AI 建议/ }));

    await screen.findByText("巷子口·本地回头客");
    await userEvent.click(screen.getByText("巷子口·本地回头客"));
    expect(screen.getByDisplayValue("巷子口·本地回头客")).toBeInTheDocument();
  });

  it("按建议优化更新简介并提供昵称候选", async () => {
    mocked(profileService.get).mockResolvedValue({
      data: defaultProfile({ health_check: healthResult }),
    });
    mocked(profileService.rewriteByHealthCheck).mockResolvedValue({
      data: {
        nickname_options: ["优化昵称"],
        bio: "优化后的简介",
        pinned_notes: [],
        bio_flagged: false,
      },
    });

    renderPage();
    await screen.findByText("一眼看出是火锅店");

    await userEvent.click(screen.getByRole("button", { name: /按建议优化/ }));
    expect(await screen.findByDisplayValue("优化后的简介")).toBeInTheDocument();
    expect(screen.getByText("优化昵称")).toBeInTheDocument();
  });

  it("保存草稿携带置顶笔记", async () => {
    mocked(profileService.get).mockResolvedValue({
      data: defaultProfile({
        pinned_notes: [{ title: "怎么找到我们", content: "评论区扣1" }],
      }),
    });

    renderPage();
    await screen.findByDisplayValue("怎么找到我们");

    await userEvent.click(screen.getByRole("button", { name: /保存草稿/ }));
    await waitFor(() => {
      expect(profileService.update).toHaveBeenCalledWith(
        "shop-1",
        "xiaohongshu",
        expect.objectContaining({
          nickname: "巷子口老灶火锅",
          pinned_notes: [{ title: "怎么找到我们", content: "评论区扣1" }],
        })
      );
    });
  });

  it("简介命中审核时复制需二次确认", async () => {
    mocked(profileService.get).mockResolvedValue({
      data: defaultProfile({ bio: "加微信刷单", bio_flagged: true }),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    let captured: { onOk?: () => void } = {};
    const confirmSpy = vi.spyOn(Modal, "confirm").mockImplementation((config) => {
      captured = config as { onOk?: () => void };
      return { destroy: vi.fn() } as never;
    });

    renderPage();
    await screen.findByDisplayValue("加微信刷单");

    await userEvent.click(screen.getByRole("button", { name: /一键复制全部文案/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await captured.onOk?.();
    });
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining("加微信刷单"));
    });
  });

  it("上传截图返回多个复刻方案时可点选应用", async () => {
    mocked(profileService.analyzeStyle).mockResolvedValue({
      data: {
        vibe: "市井烟火",
        dominant_colors: ["#C93828"],
        schemes: [
          {
            id: "A",
            name: "暖辣市井方案",
            color_scheme: {
              primary: "#C93828",
              secondary: "#FFF0EE",
              accent: "#A82015",
              text: "#2A0A08",
            },
            style_keywords: ["复古", "烟火气"],
            nickname_options: ["巷子口老灶火锅"],
            bio: "人均80吃撑",
            avatar_prompt: "红铜锅头像",
            bg_prompt: "老巷子背景",
          },
        ],
      },
    });

    renderPage();
    await screen.findByDisplayValue("巷子口老灶火锅");

    const uploadBtn = screen.getByRole("button", { name: /上传截图/ });
    const uploadWrap = uploadBtn.closest(".ant-upload") as HTMLElement;
    const input = uploadWrap.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "home.png", { type: "image/png" }));

    await screen.findByText("复刻参考方案 · 市井烟火");
    await userEvent.click(screen.getByText("暖辣市井方案"));
    expect(await screen.findByDisplayValue("红铜锅头像")).toBeInTheDocument();
    expect(screen.getByDisplayValue("巷子口老灶火锅")).toBeInTheDocument();
  });
});
