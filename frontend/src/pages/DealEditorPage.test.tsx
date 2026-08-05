// 团购工坊编辑器测试 — 毛利展示 / 生成二次确认 / 平台 Tab 状态 / 归档只读
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DealScheme, DealSchemeCopy } from "../services/deals";
import { dealService } from "../services/deals";
import { shopService } from "../services/shops";
import DealEditorPage from "./DealEditorPage";

vi.mock("../services/deals", () => ({
  dealService: {
    getProject: vi.fn(),
    listItems: vi.fn(),
    listCompetitors: vi.fn(),
    listSchemes: vi.fn(),
    generateSchemes: vi.fn(),
    generateCopy: vi.fn(),
    updateCopy: vi.fn(),
    exportToDesign: vi.fn(),
    updateScheme: vi.fn(),
    deleteScheme: vi.fn(),
    createItem: vi.fn(),
    updateItem: vi.fn(),
    deleteItem: vi.fn(),
    uploadItemImage: vi.fn(),
    createCompetitor: vi.fn(),
    updateCompetitor: vi.fn(),
    deleteCompetitor: vi.fn(),
  },
}));

vi.mock("../services/shops", () => ({
  shopService: { get: vi.fn() },
}));

const project = {
  id: "proj-1",
  shop_id: "shop-1",
  title: "抖音暑期套餐",
  platform: "douyin",
  price_band: "人均80",
  status: "generated",
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

const items = [
  {
    id: "i1",
    project_id: "proj-1",
    name: "招牌毛肚",
    category: "signature",
    cost_price: "20.00",
    sale_price: "68.00",
    is_signature: true,
    is_high_margin: false,
    image_url: null,
    created_at: "2026-08-05T00:00:00Z",
    updated_at: "2026-08-05T00:00:00Z",
  },
];

const competitors = [
  {
    id: "cd1",
    project_id: "proj-1",
    name: "隔壁双人餐",
    price: "99.00",
    items_summary: "毛肚+肥牛",
    note: null,
    created_at: "2026-08-05T00:00:00Z",
    updated_at: "2026-08-05T00:00:00Z",
  },
];

const profitScheme = (over: Partial<DealScheme> = {}): DealScheme => ({
  id: "s1",
  project_id: "proj-1",
  scheme_type: "profit",
  generation_batch: 1,
  title: "利润款·双人招牌套餐",
  description: "招牌+高毛利",
  items: [
    { item_id: "i1", name: "招牌毛肚", qty: 1, sale_price: 68, cost_price: 20 },
    { item_id: "i2", name: "雪花肥牛", qty: 1, sale_price: 58, cost_price: 25 },
  ],
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
  copies: [],
  ...over,
});

const douyinCopy: DealSchemeCopy = {
  id: "c1",
  scheme_id: "s1",
  platform: "douyin",
  title: "9.9吃招牌！现炒火锅单人餐",
  selling_points: ["现炒底料", "30分钟出餐"],
  rules: "仅限工作日午餐",
  cover_prompt: "cover prompt",
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/deals/proj-1"]}>
      <Routes>
        <Route path="/deals/:id" element={<DealEditorPage />} />
      </Routes>
    </MemoryRouter>
  );
}

async function openSchemesTab() {
  await screen.findByText("抖音暑期套餐");
  await userEvent.click(screen.getByRole("tab", { name: "套餐方案" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  (dealService.getProject as ReturnType<typeof vi.fn>).mockResolvedValue({ data: project });
  (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
  (dealService.listItems as ReturnType<typeof vi.fn>).mockResolvedValue({
    data: { items, total: 1, page: 1, size: 20 },
  });
  (dealService.listCompetitors as ReturnType<typeof vi.fn>).mockResolvedValue({
    data: { items: competitors, total: 1, page: 1, size: 20 },
  });
  (dealService.listSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
});


describe("DealEditorPage", () => {
  it("展示毛利两行（gross/net）+ 佣金率与负毛利警示", async () => {
    (dealService.listSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        profitScheme(),
        profitScheme({
          id: "s2",
          scheme_type: "scenario",
          title: "场景款·宵夜",
          original_price: "24.00",
          deal_price: "19.90",
          cost_estimate: "4.00",
          margin_estimate: {
            gross_margin: 0.1,
            platform_commission_rate: 0.06,
            net_margin: -0.05,
            note: "净毛利为负：请重新评估组合/定价，确认后再上线",
          },
        }),
      ],
    });

    renderPage();
    await openSchemesTab();

    expect(await screen.findByText(/毛利（gross）：48\.9%/)).toBeInTheDocument();
    expect(screen.getByText(/净毛利（net）：42\.9%/)).toBeInTheDocument();
    expect(screen.getAllByText(/佣金率 6\.0%/).length).toBeGreaterThan(0);
    expect(screen.getByText(/原价 ¥126\.00 → 团购价/)).toBeInTheDocument();
    expect(screen.getByText("¥88.00")).toBeInTheDocument();
    expect(
      screen.getByText("净毛利为负：请重新评估组合/定价，确认后再上线")
    ).toBeInTheDocument();
  });

  it("首次生成（无方案）直接调用，不弹二次确认", async () => {
    const confirmSpy = vi.spyOn(Modal, "confirm").mockReturnValue({
      destroy: vi.fn(),
    } as never);
    (dealService.generateSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { generation_batch: 1, schemes: [profitScheme()] },
    });

    renderPage();
    await openSchemesTab();

    await userEvent.click(screen.getByRole("button", { name: /生成套餐方案/ }));
    await waitFor(() => {
      expect(dealService.generateSchemes).toHaveBeenCalledWith("proj-1");
    });
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("已有方案时点击生成弹二次确认（重新生成将归档）", async () => {
    (dealService.listSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [profitScheme()],
    });
    let captured: { onOk?: () => void } = {};
    const confirmSpy = vi.spyOn(Modal, "confirm").mockImplementation((config) => {
      captured = config as { onOk?: () => void };
      return { destroy: vi.fn() } as never;
    });
    (dealService.generateSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { generation_batch: 2, schemes: [profitScheme({ generation_batch: 2 })] },
    });

    renderPage();
    await openSchemesTab();

    await userEvent.click(screen.getByRole("button", { name: /生成套餐方案/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(captured)).toContain("重新生成将归档当前方案");

    await act(async () => {
      await captured.onOk?.();
    });
    await waitFor(() => {
      expect(dealService.generateSchemes).toHaveBeenCalledWith("proj-1");
    });
  });

  it("平台文案 Tab 状态独立：生成抖音只影响抖音，其余平台互不覆盖", async () => {
    (dealService.listSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [profitScheme()],
    });
    (dealService.generateCopy as ReturnType<typeof vi.fn>).mockResolvedValue({ data: douyinCopy });

    renderPage();
    await openSchemesTab();

    // 抖音 Tab 默认激活：初始显示「生成该平台文案」
    const generateBtn = await screen.findByRole("button", { name: /生成该平台文案/ });
    await userEvent.click(generateBtn);

    // 生成后抖音 Tab 展示文案内容
    expect(await screen.findByText("9.9吃招牌！现炒火锅单人餐")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /复制上线文案/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /导出该平台视觉设计/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(dealService.generateCopy).toHaveBeenCalledWith("proj-1", "s1", "douyin");
    });

    // 切到小红书：仍未生成，互不覆盖
    await userEvent.click(screen.getByRole("tab", { name: "小红书" }));
    expect(screen.getByRole("button", { name: /生成该平台文案/ })).toBeInTheDocument();

    // 切回抖音：内容仍在
    await userEvent.click(screen.getByRole("tab", { name: "抖音" }));
    expect(screen.getByText("9.9吃招牌！现炒火锅单人餐")).toBeInTheDocument();
    await waitFor(() => {
      expect(dealService.generateCopy).toHaveBeenCalledTimes(1);
    });
  });

  it("归档方案只读：无编辑按钮，文案只读展示", async () => {
    (dealService.listSchemes as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        profitScheme(),
        profitScheme({
          id: "s9",
          scheme_type: "hook",
          title: "历史引流款",
          generation_batch: 0,
          is_archived: true,
          copies: [{ ...douyinCopy, id: "c9", scheme_id: "s9", title: "历史抖音文案" }],
        }),
      ],
    });

    renderPage();
    await openSchemesTab();

    // 展开历史批次
    await userEvent.click(screen.getByText(/历史批次/));
    const archivedCard = (await screen.findByText("历史引流款")).closest(".ant-card") as HTMLElement;

    expect(within(archivedCard).getByText("只读")).toBeInTheDocument();
    expect(within(archivedCard).queryByRole("button", { name: /编辑方案/ })).toBeNull();
    expect(within(archivedCard).queryByRole("button", { name: /生成该平台文案/ })).toBeNull();
    expect(within(archivedCard).getByText("历史抖音文案")).toBeInTheDocument();

    // 活跃方案才有编辑按钮
    expect(screen.getAllByRole("button", { name: /编辑方案/ })).toHaveLength(1);
  });
});



