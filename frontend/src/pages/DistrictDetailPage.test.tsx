// 商圈分析详情页组件测试 — loading/概览统计/重新分析/429 冷却/状态过滤
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { shopService } from "../services/shops";
import { districtService } from "../services/district";
import DistrictDetailPage from "./DistrictDetailPage";

vi.mock("../services/shops", () => ({
  shopService: { get: vi.fn() },
}));

vi.mock("../services/district", () => ({
  districtService: {
    analyze: vi.fn(),
    latest: vi.fn(),
    listSnapshots: vi.fn(),
    snapshotDetail: vi.fn(),
    listPois: vi.fn(),
    competitors: vi.fn(),
    listOverrides: vi.fn(),
    setPoiOverride: vi.fn(),
    deletePoiOverride: vi.fn(),
    mapConfig: vi.fn(),
  },
}));

vi.mock("../components/district/AmapView", () => ({
  default: () => <div data-testid="amap-view" />,
}));

const shop = {
  id: "shop-1",
  merchant_id: "m1",
  name: "测试火锅店",
  address: "武汉市江岸区沿江大道144号",
  phone: null,
  category: "火锅",
  status: "active",
  created_at: "2026-08-04T00:00:00Z",
};

const snapshot = {
  id: "snap-1",
  shop_id: "shop-1",
  center_lng: 114.29,
  center_lat: 30.58,
  geocode_level: "门牌号",
  radius_m: 3000,
  poi_total: 42,
  competitor_count: 8,
  category_stats: [
    { category: "火锅店", count: 8 },
    { category: "奶茶店", count: 3 },
  ],
  density_per_km2: 1.49,
  mapping_status: "full",
  status: "analyzed",
  error_message: null,
  excluded_self_count: 1,
  created_at: "2026-08-04T00:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/district/shop-1"]}>
      <Routes>
        <Route path="/district/:shop_id" element={<DistrictDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DistrictDetailPage", () => {
  it("加载后渲染门店信息、概览统计与竞品列表", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>).mockResolvedValue({ data: snapshot });
    (districtService.snapshotDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ...snapshot, pois: [] },
    });
    (districtService.competitors as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        {
          poi_id: "B0001",
          name: "秋孃孃火锅",
          category: "火锅店",
          address: "解放碑83号",
          distance_m: 83,
          lng: 114.3,
          lat: 30.58,
        },
      ],
    });
    (districtService.listPois as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20 },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [snapshot], total: 1, page: 1, size: 10 },
    });

    renderPage();

    await screen.findByText("测试火锅店");
    // 异步加载的概览/竞品/品类分布
    expect(await screen.findByText("秋孃孃火锅")).toBeInTheDocument();
    expect(await screen.findByText("1.49 家/km²")).toBeInTheDocument();
    expect(screen.getAllByText("火锅店").length).toBeGreaterThan(0);
    expect(screen.getByText("奶茶店")).toBeInTheDocument();
    // 地图 stub
    expect(screen.getByTestId("amap-view")).toBeInTheDocument();
  });

  it("无快照时展示空态与开始分析按钮", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>).mockRejectedValue({
      response: { status: 404 },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 10 },
    });

    renderPage();

    expect(await screen.findByText("暂无商圈快照，点击「开始分析」生成周边 3km 商圈数据")).toBeInTheDocument();
  });

  it("点击重新分析调用 analyze 并刷新最新快照", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: snapshot })
      .mockResolvedValue({ data: snapshot });
    (districtService.snapshotDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ...snapshot, pois: [] },
    });
    (districtService.competitors as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (districtService.listPois as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20 },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [snapshot], total: 1, page: 1, size: 10 },
    });
    (districtService.analyze as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { snapshot_id: "snap-2", poi_total: 50, competitor_count: 9, density_per_km2: 1.8, mapping_status: "full", excluded_self_count: 0 },
    });

    renderPage();
    await screen.findByText("测试火锅店");

    const btn = screen.getByRole("button", { name: /重新分析/ });
    await userEvent.click(btn);

    await waitFor(() => {
      expect(districtService.analyze).toHaveBeenCalledWith("shop-1");
    });
  });

  it("analyze 返回 429 时进入冷却倒计时", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>).mockResolvedValue({ data: snapshot });
    (districtService.snapshotDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ...snapshot, pois: [] },
    });
    (districtService.competitors as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (districtService.listPois as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20 },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [snapshot], total: 1, page: 1, size: 10 },
    });
    (districtService.analyze as ReturnType<typeof vi.fn>).mockRejectedValue({
      response: { status: 429, data: { detail: "操作过于频繁，请 60 秒后重试" } },
    });

    renderPage();
    await screen.findByText("测试火锅店");

    const btn = screen.getByRole("button", { name: /重新分析/ });
    await userEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /重新分析（\d+s）/ })).toBeInTheDocument();
    });
  });

  it("切换失败快照按 status=failed 过滤历史", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>).mockResolvedValue({ data: snapshot });
    (districtService.snapshotDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ...snapshot, pois: [] },
    });
    (districtService.competitors as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    (districtService.listPois as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20 },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 10 },
    });

    renderPage();
    await screen.findByText("测试火锅店");

    const failedSegment = screen.getByText("失败");
    await userEvent.click(failedSegment);

    await waitFor(() => {
      expect(districtService.listSnapshots).toHaveBeenCalledWith("shop-1", {
        page: 1,
        size: 10,
        status: "failed",
      });
    });
  });

  it("手动标记竞品/非竞品并刷新", async () => {
    (shopService.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: shop });
    (districtService.latest as ReturnType<typeof vi.fn>).mockResolvedValue({ data: snapshot });
    (districtService.snapshotDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        ...snapshot,
        pois: [
          { id: "r1", poi_id: "p-hotpot", name: "隔壁火锅", category: "火锅店", typecode: "050117", lng: 114.3, lat: 30.58, distance_m: 100, is_competitor: true, excluded_as_self: false },
          { id: "r2", poi_id: "p-coffee", name: "咖啡小馆", category: "咖啡厅", typecode: "050500", lng: 114.29, lat: 30.58, distance_m: 200, is_competitor: false, excluded_as_self: false },
        ],
      },
    });
    (districtService.competitors as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        { poi_id: "p-hotpot", name: "隔壁火锅", category: "火锅店", distance_m: 100, lng: 114.3, lat: 30.58 },
      ],
    });
    (districtService.listPois as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        items: [
          { id: "r1", poi_id: "p-hotpot", name: "隔壁火锅", category: "火锅店", typecode: "050117", lng: 114.3, lat: 30.58, distance_m: 100, is_competitor: true, excluded_as_self: false },
          { id: "r2", poi_id: "p-coffee", name: "咖啡小馆", category: "咖啡厅", typecode: "050500", lng: 114.29, lat: 30.58, distance_m: 200, is_competitor: false, excluded_as_self: false },
        ],
        total: 2,
        page: 1,
        size: 20,
      },
    });
    (districtService.listSnapshots as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { items: [snapshot], total: 1, page: 1, size: 10 },
    });

    renderPage();
    await screen.findByText("测试火锅店");
    await screen.findAllByText("隔壁火锅");

    // 把非竞品「咖啡小馆」设为竞品
    const setBtn = screen.getByRole("button", { name: "设为竞品" });
    await userEvent.click(setBtn);

    await waitFor(() => {
      expect(districtService.setPoiOverride).toHaveBeenCalledWith(
        "shop-1",
        "p-coffee",
        { is_competitor: true, poi_name: "咖啡小馆" }
      );
    });
    // 标记后刷新：latest / snapshotDetail / competitors 重新拉取
    await waitFor(() => {
      expect(districtService.competitors).toHaveBeenCalledTimes(2);
    });
  });
});
