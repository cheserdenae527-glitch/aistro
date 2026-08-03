import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, List, Spin, Typography, Tag } from "antd";
import { ShopOutlined } from "@ant-design/icons";
import { merchantService } from "../services/merchants";
import { shopService } from "../services/shops";
import type { Merchant, MerchantWithShops } from "../services/merchants";
import type { Shop } from "../services/shops";

const { Title, Text } = Typography;

export default function ProfileIndexPage() {
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
          // 批量接口不可用时回退：商家 + 门店并发拉取
          const listRes = await merchantService.list({ size: 100 });
          const merchants = listRes.data.items;
          const all: MerchantWithShops[] = await Promise.all(
            merchants.map(async (m) => ({
              merchant: m,
              shops: (await shopService.listByMerchant(m.id)).data,
            }))
          );
          setData(all);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={{ textAlign: "center", padding: 80 }}><Spin size="large" /></div>;

  return (
    <div>
      <Title level={4}>账号装修 — 选择门店</Title>
      <Text type="secondary" style={{ marginBottom: 24, display: "block" }}>
        选择一个门店，开始设计小红书 Profile 装修方案
      </Text>

      {data.length === 0 && <Text type="secondary">暂无商家和门店数据</Text>}

      {data.map(({ merchant, shops }) => (
        <Card
          key={merchant.id}
          title={<span><ShopOutlined /> {merchant.name}</span>}
          style={{ marginBottom: 16 }}
        >
          <List
            dataSource={shops}
            renderItem={(shop) => (
              <List.Item
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/shops/${shop.id}/profile/xiaohongshu`)}
              >
                <List.Item.Meta
                  title={shop.name}
                  description={shop.address || "—"}
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
