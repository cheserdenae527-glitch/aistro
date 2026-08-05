import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Modal,
  Select,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ShopOutlined,
} from "@ant-design/icons";
import { merchantService, type MerchantWithShops } from "../services/merchants";
import { shopService, type Shop } from "../services/shops";
import { liveService, type LivePlatform, type LiveProject } from "../services/live";
import { PLATFORM_LABELS } from "../utils/live";
import { showApiError } from "../utils/errors";

const { Title, Text } = Typography;

interface ShopGroup {
  merchant: MerchantWithShops["merchant"];
  shops: { shop: Shop; projects: LiveProject[] }[];
}

const PLATFORM_OPTIONS: { value: LivePlatform; label: string }[] = [
  { value: "douyin", label: "抖音" },
  { value: "xiaohongshu", label: "小红书" },
  { value: "wechat", label: "视频号" },
];

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已归档",
};

export default function LiveIndexPage() {
  const navigate = useNavigate();
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState<ShopGroup[]>([]);
  const [creatingShop, setCreatingShop] = useState<Shop | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newPlatform, setNewPlatform] = useState<LivePlatform>("douyin");
  const [newGoal, setNewGoal] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      let merchants: MerchantWithShops[];
      try {
        merchants = (await merchantService.listWithShops()).data;
      } catch {
        const listRes = await merchantService.list({ size: 100 });
        merchants = await Promise.all(
          listRes.data.items.map(async (merchant) => ({
            merchant,
            shops: (await shopService.listByMerchant(merchant.id)).data,
          }))
        );
      }
      const rows = await Promise.all(
        merchants.map(async (entry) => ({
          merchant: entry.merchant,
          shops: await Promise.all(
            entry.shops.map(async (shop) => ({
              shop,
              projects: (
                await liveService.listProjects({ shop_id: shop.id, page: 1, page_size: 100 })
              ).data.items,
            }))
          ),
        }))
      );
      setGroups(rows);
    } catch {
      // 保留空态
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, []);

  const handleCreate = async () => {
    if (!creatingShop || !newTitle.trim()) return;
    setCreating(true);
    try {
      const res = await liveService.createProject({
        shop_id: creatingShop.id,
        title: newTitle.trim(),
        platform: newPlatform,
        goal: newGoal.trim() || null,
      });
      navigate(`/live/${res.data.id}`);
    } catch (e) {
      showApiError(e);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (project: LiveProject) => {
    try {
      await liveService.deleteProject(project.id);
      await load();
    } catch (e) {
      showApiError(e);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <Title level={4}>直播工坊 — 项目列表</Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 20 }}>
        项目（门店+平台+目标）→ 数字人形象 → AI 脚本 → 弹幕规则 → 合规定稿 → 导出开播包 → 场次复盘
      </Text>

      {groups.length === 0 && (
        <Card>
          <Empty description="暂无商家和门店数据" />
        </Card>
      )}

      {groups.map((group) => (
        <Card
          key={group.merchant.id}
          title={
            <span>
              <ShopOutlined /> {group.merchant.name}
            </span>
          }
          style={{ marginBottom: 16 }}
        >
          {group.shops.map(({ shop, projects }) => (
            <div
              key={shop.id}
              style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, marginBottom: 10 }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <Text strong>{shop.name}</Text>
                <Tag color="blue">{shop.address || "未填写地址"}</Tag>
                <Button
                  size="small"
                  type="primary"
                  ghost
                  icon={<PlusOutlined />}
                  onClick={() => {
                    setCreatingShop(shop);
                    setNewTitle("");
                    setNewPlatform("douyin");
                    setNewGoal("");
                  }}
                >
                  新建项目
                </Button>
              </div>
              <List
                size="small"
                dataSource={projects}
                locale={{ emptyText: "暂无直播项目" }}
                renderItem={(project) => (
                  <List.Item
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/live/${project.id}`)}
                    actions={[
                      <Button
                        key="edit"
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/live/${project.id}`);
                        }}
                      >
                        打开
                      </Button>,
                      <Button
                        key="delete"
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(project);
                        }}
                      >
                        删除
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={project.title}
                      description={
                        <>
                          <Tag color="geekblue">
                            {PLATFORM_LABELS[project.platform] || project.platform}
                          </Tag>
                          <Tag>{STATUS_LABELS[project.status] || project.status}</Tag>
                          {project.ai_label_text && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {project.ai_label_text}
                            </Text>
                          )}
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            </div>
          ))}
        </Card>
      ))}

      <Modal
        title={`新建直播项目 — ${creatingShop?.name || ""}`}
        open={!!creatingShop}
        onOk={handleCreate}
        confirmLoading={creating}
        onCancel={() => setCreatingShop(null)}
        okText="创建并进入"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
          <div>
            <Text type="secondary">项目名</Text>
            <Input
              placeholder="如：火锅直播间"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              maxLength={100}
            />
          </div>
          <div>
            <Text type="secondary">主平台</Text>
            <Select
              style={{ width: "100%" }}
              value={newPlatform}
              onChange={(v) => setNewPlatform(v)}
              options={PLATFORM_OPTIONS}
            />
          </div>
          <div>
            <Text type="secondary">场次目标（可选）</Text>
            <Input
              placeholder="如：提升核销"
              value={newGoal}
              onChange={(e) => setNewGoal(e.target.value)}
              maxLength={2000}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
