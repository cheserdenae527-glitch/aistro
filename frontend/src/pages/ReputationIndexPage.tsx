import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, List, Spin, Tag, Typography } from "antd";
import { CommentOutlined, ShopOutlined } from "@ant-design/icons";
import { merchantService } from "../services/merchants";
import { shopService } from "../services/shops";
import type { Merchant } from "../services/merchants";
import type { Shop } from "../services/shops";

const { Title, Text } = Typography;

export default function ReputationIndexPage() {
  const navigate = useNavigate();
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{ merchant: Merchant; shops: Shop[] }[]>([]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        try {
          const res = await merchantService.listWithShops();
          setData(res.data);
        } catch {
          const listRes = await merchantService.list({ size: 100 });
          const merchants = listRes.data.items;
          const rows = await Promise.all(
            merchants.map(async (merchant) => ({
              merchant,
              shops: (await shopService.listByMerchant(merchant.id)).data,
            }))
          );
          setData(rows);
        }
      } catch {
        // 保留空态
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <Title level={4}>口碑管理 — 选择门店</Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 20 }}>
        聚合小红书笔记与评论，分析口碑、生成回复、处理差评预警
      </Text>

      {data.length === 0 && <Text type="secondary">暂无商家和门店数据</Text>}

      {data.map(({ merchant, shops }) => (
        <Card
          key={merchant.id}
          title={
            <span>
              <ShopOutlined /> {merchant.name}
            </span>
          }
          style={{ marginBottom: 16 }}
        >
          <List
            dataSource={shops}
            renderItem={(shop) => (
              <List.Item
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/reputation/${shop.id}`)}
              >
                <List.Item.Meta
                  avatar={
                    <div
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 6,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "#eef4ff",
                        color: "#1677ff",
                        fontSize: 16,
                      }}
                    >
                      <CommentOutlined />
                    </div>
                  }
                  title={shop.name}
                  description={
                    <>
                      {shop.category && <Tag>{shop.category}</Tag>}
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {shop.address || "未填写地址"}
                      </Text>
                    </>
                  }
                />
                <Tag color="blue">小红书</Tag>
              </List.Item>
            )}
            locale={{ emptyText: "该商家下暂无门店" }}
          />
        </Card>
      ))}
    </div>
  );
}
