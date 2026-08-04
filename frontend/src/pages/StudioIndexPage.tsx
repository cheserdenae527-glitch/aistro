import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Modal,
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
import { studioService, type StudioProject } from "../services/studio";
import { showApiError } from "../utils/errors";

const { Title, Text } = Typography;

interface ShopGroup {
  merchant: MerchantWithShops["merchant"];
  shops: { shop: Shop; projects: StudioProject[] }[];
}

export default function StudioIndexPage() {
  const navigate = useNavigate();
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState<ShopGroup[]>([]);
  const [creatingShop, setCreatingShop] = useState<Shop | null>(null);
  const [newTitle, setNewTitle] = useState("");
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
              projects: (await studioService.listProjects(shop.id)).data,
            }))
          ),
        }))
      );
      setGroups(rows);
    } catch {
      // ignore: 页面保留空态
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
      const res = await studioService.createProject({
        shop_id: creatingShop.id,
        title: newTitle.trim(),
      });
      navigate(`/studio/${res.data.id}`);
    } catch (e) {
      showApiError(e);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (project: StudioProject) => {
    try {
      await studioService.deleteProject(project.id);
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
      <Title level={4}>内容工坊 — 项目列表</Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 20 }}>
        文案生成 → 小红书卡组渲染 → 导出到视觉设计，一条流水线完成
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
              style={{
                border: "1px solid #eee",
                borderRadius: 8,
                padding: 12,
                marginBottom: 10,
              }}
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
                  }}
                >
                  新建项目
                </Button>
              </div>
              <List
                size="small"
                dataSource={projects}
                locale={{ emptyText: "暂无内容工坊项目" }}
                renderItem={(project) => (
                  <List.Item
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/studio/${project.id}`)}
                    actions={[
                      <Button
                        key="edit"
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/studio/${project.id}`);
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
                          <Tag color={project.status === "generated" ? "green" : "default"}>
                            {project.status === "generated" ? "已生成文案" : "草稿"}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {new Date(project.created_at).toLocaleString("zh-CN")}
                          </Text>
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
        open={!!creatingShop}
        title={`新建内容工坊项目 — ${creatingShop?.name || ""}`}
        onCancel={() => setCreatingShop(null)}
        onOk={handleCreate}
        okText="创建并开始创作"
        confirmLoading={creating}
        okButtonProps={{ disabled: !newTitle.trim() }}
      >
        <Input
          placeholder="项目名称，例如：小红书开业卡组"
          value={newTitle}
          maxLength={100}
          onChange={(e) => setNewTitle(e.target.value)}
          onPressEnter={handleCreate}
        />
      </Modal>
    </div>
  );
}
