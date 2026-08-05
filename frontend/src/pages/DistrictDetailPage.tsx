// 商圈分析详情页 — 地图 + 概览 + 品类分布 + 竞品列表 + POI 明细 + 历史快照
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  message,
  Pagination,
  Row,
  Segmented,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import {
  ArrowLeftOutlined,
  EnvironmentOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import AmapView, { type MapPoint } from "../components/district/AmapView";
import { shopService, type Shop } from "../services/shops";
import {
  districtService,
  type Competitor,
  type Poi,
  type SnapshotDetail,
  type SnapshotStatus,
  type SnapshotSummary,
} from "../services/district";
import { getApiError, showApiError } from "../utils/errors";
import {
  categoryCount,
  formatDensity,
  formatDistance,
  formatTime,
  sortCategoryStats,
} from "../utils/district";

const { Title, Text } = Typography;

const RATE_COOLDOWN_SECONDS = 60;
const HISTORY_SIZE = 10;
const POI_SIZE = 20;

export default function DistrictDetailPage() {
  const { shop_id } = useParams<{ shop_id: string }>();
  const shopId = shop_id ?? "";
  const navigate = useNavigate();
  const startedRef = useRef(false);

  const [shop, setShop] = useState<Shop | null>(null);
  const [latest, setLatest] = useState<SnapshotSummary | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotDetail | null>(null);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);

  const [pois, setPois] = useState<Poi[]>([]);
  const [poisTotal, setPoisTotal] = useState(0);
  const [poisPage, setPoisPage] = useState(1);
  const [includeExcluded, setIncludeExcluded] = useState(false);

  const [history, setHistory] = useState<SnapshotSummary[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyStatus, setHistoryStatus] = useState<SnapshotStatus>("analyzed");

  const [pageLoading, setPageLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [markingPoiId, setMarkingPoiId] = useState<string | null>(null);

  // ---------- 初始加载：门店 + 最新快照 + 历史 ----------
  useEffect(() => {
    if (startedRef.current || !shopId) return;
    startedRef.current = true;
    (async () => {
      try {
        const shopRes = await shopService.get(shopId);
        setShop(shopRes.data);
      } catch (e) {
        message.error(getApiError(e));
        setPageLoading(false);
        return;
      }
      try {
        const latestRes = await districtService.latest(shopId);
        setLatest(latestRes.data);
        setSelectedId(latestRes.data.id);
      } catch {
        // 404：尚无快照
      }
      setPageLoading(false);
    })();
  }, [shopId]);

  // ---------- 选中快照 → 详情 + 竞品 ----------
  useEffect(() => {
    if (!selectedId || !shopId) return;
    let cancelled = false;
    setDetailLoading(true);
    (async () => {
      try {
        const [detailRes, compRes] = await Promise.all([
          districtService.snapshotDetail(shopId, selectedId),
          districtService.competitors(shopId, selectedId),
        ]);
        if (cancelled) return;
        setSnapshot(detailRes.data);
        setCompetitors(compRes.data);
        setPois(detailRes.data.pois);
        setPoisTotal(detailRes.data.poi_total);
        setPoisPage(1);
      } catch (e) {
        if (!cancelled) showApiError(e);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [shopId, selectedId]);

  // ---------- POI 分页 / 展开自身 ----------
  useEffect(() => {
    if (!selectedId || !shopId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await districtService.listPois(shopId, selectedId, {
          page: poisPage,
          size: POI_SIZE,
          include_excluded: includeExcluded || undefined,
        });
        if (cancelled) return;
        setPois(res.data.items);
        setPoisTotal(res.data.total);
      } catch {
        // 忽略分页错误
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [shopId, selectedId, poisPage, includeExcluded]);

  // ---------- 历史快照列表 ----------
  const loadHistory = useCallback(
    async (page: number, status: SnapshotStatus) => {
      if (!shopId) return;
      setHistoryLoading(true);
      try {
        const res = await districtService.listSnapshots(shopId, {
          page,
          size: HISTORY_SIZE,
          status,
        });
        setHistory(res.data.items);
        setHistoryTotal(res.data.total);
        setHistoryPage(res.data.page);
      } catch {
        showApiError;
      } finally {
        setHistoryLoading(false);
      }
    },
    [shopId]
  );

  useEffect(() => {
    loadHistory(1, historyStatus);
  }, [loadHistory, historyStatus]);

  // ---------- 429 冷却倒计时 ----------
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((c) => Math.max(0, c - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const refreshAfterAnalyze = useCallback(
    async (snapshotId: string) => {
      setLatest(await districtService.latest(shopId).then((r) => r.data));
      setSelectedId(snapshotId);
      loadHistory(1, historyStatus);
    },
    [shopId, historyStatus, loadHistory]
  );

  const reloadAfterMark = useCallback(async () => {
    if (!shopId || !selectedId) return;
    const [latestRes, detailRes, compRes] = await Promise.all([
      districtService.latest(shopId),
      districtService.snapshotDetail(shopId, selectedId),
      districtService.competitors(shopId, selectedId),
    ]);
    setLatest(latestRes.data);
    setSnapshot(detailRes.data);
    setCompetitors(compRes.data);
    setPois(detailRes.data.pois);
    setPoisTotal(detailRes.data.poi_total);
    setPoisPage(1);
  }, [shopId, selectedId]);

  const handleSetCompetitor = async (poi: { poi_id: string; name: string }, isCompetitor: boolean) => {
    if (!shopId || markingPoiId) return;
    setMarkingPoiId(poi.poi_id);
    try {
      await districtService.setPoiOverride(shopId, poi.poi_id, {
        is_competitor: isCompetitor,
        poi_name: poi.name,
      });
      message.success(isCompetitor ? "已设为竞品" : "已设为非竞品");
      await reloadAfterMark();
    } catch (e) {
      showApiError(e);
    } finally {
      setMarkingPoiId(null);
    }
  };

  const handleClearOverride = async (comp: Competitor) => {
    if (!shopId || markingPoiId) return;
    setMarkingPoiId(comp.poi_id);
    try {
      await districtService.deletePoiOverride(shopId, comp.poi_id);
      message.success("已取消手动标记，还原为自动判定");
      await reloadAfterMark();
    } catch (e) {
      showApiError(e);
    } finally {
      setMarkingPoiId(null);
    }
  };

  const handleAnalyze = async () => {
    if (!shopId || analyzing || cooldown > 0) return;
    setAnalyzing(true);
    try {
      const res = await districtService.analyze(shopId);
      message.success("商圈分析完成");
      await refreshAfterAnalyze(res.data.snapshot_id);
    } catch (e) {
      const status =
        e && typeof e === "object" && "response" in e
          ? (e as { response?: { status?: number } }).response?.status
          : undefined;
      if (status === 429) {
        setCooldown(RATE_COOLDOWN_SECONDS);
        message.warning("操作过于频繁，请 60 秒后重试");
      } else {
        showApiError(e);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  // ---------- 渲染 ----------
  if (pageLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!shop) {
    return (
      <div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/district")} style={{ marginBottom: 16 }}>
          返回门店列表
        </Button>
        <Empty description="门店不存在或无权访问" />
      </div>
    );
  }

  const mapPoints: MapPoint[] = [];
  if (snapshot && snapshot.status === "analyzed") {
    for (const c of competitors) {
      if (c.lng !== null && c.lat !== null) {
        mapPoints.push({ lng: c.lng, lat: c.lat, name: c.name, kind: "competitor" });
      }
    }
    for (const p of pois) {
      if (p.lng !== null && p.lat !== null && !p.is_competitor) {
        mapPoints.push({ lng: p.lng, lat: p.lat, name: p.name, kind: "poi" });
      }
    }
  }
  const center =
    snapshot && snapshot.center_lng !== null && snapshot.center_lat !== null
      ? { lng: snapshot.center_lng, lat: snapshot.center_lat }
      : null;

  const categoryRows = sortCategoryStats(snapshot?.category_stats ?? null);
  const maxCategoryCount = categoryRows.length > 0 ? categoryRows[0].count : 1;

  const poiColumns: TableProps<Poi>["columns"] = [
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    {
      title: "品类",
      dataIndex: "category",
      key: "category",
      width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "评分",
      dataIndex: "rating",
      key: "rating",
      width: 80,
      render: (v: number | null) => (v != null ? <Text type={v >= 4 ? "success" : undefined}>★{v.toFixed(1)}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: "人均",
      dataIndex: "cost",
      key: "cost",
      width: 80,
      render: (v: number | null) => (v != null ? `¥${v.toFixed(0)}` : <Text type="secondary">—</Text>),
    },
    {
      title: "营业时间",
      dataIndex: "business_hours",
      key: "business_hours",
      width: 180,
      ellipsis: true,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "距离",
      dataIndex: "distance_m",
      key: "distance_m",
      width: 90,
      render: (v: number) => formatDistance(v),
    },
    {
      title: "标签",
      key: "tags",
      width: 160,
      render: (_: unknown, row: Poi) => (
        <Space size={4} wrap>
          {row.is_competitor && <Tag color="red">竞品</Tag>}
          {row.is_competitor_manual && <Tag color="purple">手动</Tag>}
          {row.excluded_as_self && <Tag color="orange">疑似自身</Tag>}
        </Space>
      ),
    },
    {
      title: "竞品标记",
      key: "mark",
      width: 120,
      render: (_: unknown, row: Poi) =>
        row.is_competitor ? (
          <Button size="small" danger loading={markingPoiId === row.poi_id} onClick={() => handleSetCompetitor(row, false)}>
            设为非竞品
          </Button>
        ) : (
          <Button size="small" type="primary" ghost loading={markingPoiId === row.poi_id} onClick={() => handleSetCompetitor(row, true)}>
            设为竞品
          </Button>
        ),
    },
  ];

  const competitorColumns: TableProps<Competitor>["columns"] = [
    { title: "名称", dataIndex: "name", key: "name", ellipsis: true },
    {
      title: "品类",
      dataIndex: "category",
      key: "category",
      width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "距离",
      dataIndex: "distance_m",
      key: "distance_m",
      width: 90,
      render: (v: number) => formatDistance(v),
    },
    {
      title: "评分",
      dataIndex: "rating",
      key: "rating",
      width: 80,
      render: (v: number | null) => (v != null ? <Text type={v >= 4 ? "success" : undefined}>★{v.toFixed(1)}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: "人均",
      dataIndex: "cost",
      key: "cost",
      width: 80,
      render: (v: number | null) => (v != null ? `¥${v.toFixed(0)}` : <Text type="secondary">—</Text>),
    },
    {
      title: "营业时间",
      dataIndex: "business_hours",
      key: "business_hours",
      width: 200,
      ellipsis: true,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "商圈",
      dataIndex: "business_area",
      key: "business_area",
      width: 90,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: "电话",
      dataIndex: "tel",
      key: "tel",
      width: 130,
      render: (v: string | null) => (v ? <a href={`tel:${v}`}>{v}</a> : <Text type="secondary">—</Text>),
    },
    {
      title: "高德分类码",
      dataIndex: "typecode",
      key: "typecode",
      width: 110,
      render: (v: string | null) => (v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>),
    },
    {
      title: "标记",
      key: "manual",
      width: 70,
      render: (_: unknown, row: Competitor) =>
        row.is_competitor_manual ? <Tag color="purple">手动</Tag> : <Text type="secondary">自动</Text>,
    },
    {
      title: "操作",
      key: "action",
      width: 150,
      render: (_: unknown, row: Competitor) => (
        <Space size={4}>
          {row.is_competitor_manual && (
            <Button size="small" loading={markingPoiId === row.poi_id} onClick={() => handleClearOverride(row)}>
              取消手动
            </Button>
          )}
          <Button size="small" danger loading={markingPoiId === row.poi_id} onClick={() => handleSetCompetitor(row, false)}>
            移出竞品
          </Button>
        </Space>
      ),
    },
    { title: "地址", dataIndex: "address", key: "address", ellipsis: true },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/district")}>
          返回
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          <EnvironmentOutlined /> {shop.name}
        </Title>
        {shop.category && <Tag color="blue">{shop.category}</Tag>}
        <Text type="secondary">{shop.address || "未填写地址"}</Text>
      </Space>

      {/* 操作区 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={analyzing}
            disabled={cooldown > 0}
            onClick={handleAnalyze}
          >
            {cooldown > 0 ? `重新分析（${cooldown}s）` : analyzing ? "分析中…" : latest ? "重新分析" : "开始分析"}
          </Button>
          <Text type="secondary">基于门店地址地理编码，聚合周边 3km 餐饮 POI（每次生成新快照，保留历史）</Text>
        </Space>
      </Card>

      {/* 无快照空态 */}
      {!snapshot && !detailLoading && (
        <Card>
          <Empty description="暂无商圈快照，点击「开始分析」生成周边 3km 商圈数据" />
        </Card>
      )}

      {/* 失败快照 */}
      {snapshot && snapshot.status === "failed" && (
        <Alert type="error" showIcon message="商圈分析失败" description={snapshot.error_message || "未知错误"} style={{ marginBottom: 16 }} />
      )}

      {snapshot && snapshot.status === "analyzed" && (
        <>
          {/* 概览卡 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="POI 总数" value={snapshot.poi_total} suffix="家" />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  已排除自身 {snapshot.excluded_self_count} 家
                </Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="品类数" value={categoryCount(snapshot.category_stats)} suffix="类" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="竞品数" value={snapshot.competitor_count} suffix="家" />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {snapshot.mapping_status === "full" ? "品类已映射" : "品类未映射"}
                </Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="商圈密度" value={formatDensity(snapshot.density_per_km2)} />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  半径 {snapshot.radius_m}m · 精度 {snapshot.geocode_level || "—"}
                </Text>
              </Card>
            </Col>
          </Row>

          {/* 地图 + 品类分布 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={14}>
              <Card title="周边餐饮分布" size="small">
                <AmapView center={center} points={mapPoints} height={360} />
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="品类分布" size="small">
                {categoryRows.length === 0 ? (
                  <Empty description="暂无品类数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div>
                    {categoryRows.map((row) => (
                      <div key={row.category} style={{ marginBottom: 10 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                          <span>{row.category}</span>
                          <Text type="secondary">{row.count} 家</Text>
                        </div>
                        <div style={{ background: "#f0f0f0", borderRadius: 4, height: 10, marginTop: 4 }}>
                          <div
                            style={{
                              width: `${Math.round((row.count / maxCategoryCount) * 100)}%`,
                              background: "#1677ff",
                              height: 10,
                              borderRadius: 4,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Col>
          </Row>

          {/* 竞品列表 */}
          <Card
            title={`竞品列表（${competitors.length}）`}
            size="small"
            style={{ marginBottom: 16 }}
          >
            {snapshot.mapping_status === "none" ? (
              <Alert
                type="info"
                showIcon
                message="当前门店品类为空或不在映射表内（mapping_status=none），无法判定竞品。请到商家详情页编辑门店、选择品类（火锅/烧烤/快餐/咖啡/甜品烘焙/日料/西餐/私房菜）后重新分析"
                style={{ marginBottom: 12 }}
              />
            ) : competitors.length === 0 ? (
              <Empty description="暂未发现竞品" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table<Competitor>
                rowKey={(row) => row.poi_id}
                columns={competitorColumns}
                dataSource={competitors}
                size="small"
                pagination={false}
              />
            )}
          </Card>

          {/* POI 明细 */}
          <Card
            title={`周边 POI（${poisTotal}）`}
            size="small"
            style={{ marginBottom: 16 }}
            extra={
              <Space>
                <Button
                  type={includeExcluded ? "primary" : "default"}
                  size="small"
                  onClick={() => {
                    setIncludeExcluded((v) => !v);
                    setPoisPage(1);
                  }}
                >
                  显示疑似自身门店
                </Button>
              </Space>
            }
          >
            <Table<Poi>
              rowKey="id"
              columns={poiColumns}
              dataSource={pois}
              size="small"
              loading={detailLoading}
              pagination={{
                current: poisPage,
                pageSize: POI_SIZE,
                total: poisTotal,
                showSizeChanger: false,
                onChange: (page) => setPoisPage(page),
              }}
            />
          </Card>
        </>
      )}

      {/* 历史快照 */}
      <Card
        title="历史快照"
        size="small"
        extra={
          <Segmented
            value={historyStatus}
            onChange={(v) => {
              setHistoryStatus(v as SnapshotStatus);
              setHistoryPage(1);
            }}
            options={[
              { label: "成功", value: "analyzed" },
              { label: "失败", value: "failed" },
            ]}
          />
        }
      >
        <Spin spinning={historyLoading}>
          {history.length === 0 ? (
            <Empty description="暂无该状态快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <>
              {history.map((h) => (
                <div
                  key={h.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "8px 0",
                    borderBottom: "1px solid #f0f0f0",
                    cursor: "pointer",
                  }}
                  onClick={() => {
                    setSelectedId(h.id);
                    setHistoryPage(1);
                  }}
                >
                  <Tag color={h.status === "analyzed" ? "green" : "red"}>
                    {h.status === "analyzed" ? "成功" : "失败"}
                  </Tag>
                  <Text strong style={{ flex: "none", width: 150 }}>
                    {formatTime(h.created_at)}
                  </Text>
                  <Text type="secondary" style={{ flex: 1, minWidth: 0 }} ellipsis>
                    {h.status === "analyzed"
                      ? `POI ${h.poi_total} · 竞品 ${h.competitor_count} · 密度 ${formatDensity(h.density_per_km2)}`
                      : (h.error_message || "失败")}
                  </Text>
                  {selectedId === h.id && <Tag color="blue">当前</Tag>}
                </div>
              ))}
              <Pagination
                current={historyPage}
                pageSize={HISTORY_SIZE}
                total={historyTotal}
                showSizeChanger={false}
                onChange={(page) => {
                  setHistoryPage(page);
                  loadHistory(page, historyStatus);
                }}
                style={{ marginTop: 12, textAlign: "right" }}
              />
            </>
          )}
        </Spin>
      </Card>
    </div>
  );
}
