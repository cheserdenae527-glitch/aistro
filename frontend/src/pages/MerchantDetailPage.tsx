import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button, Card, Descriptions, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from "antd";
import { ArrowLeftOutlined, PlusOutlined } from "@ant-design/icons";
import { merchantService, type Merchant } from "../services/merchants";
import { shopService, type Shop } from "../services/shops";

const { Title } = Typography;

export default function MerchantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [merchant, setMerchant] = useState<Merchant | null>(null);
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingShop, setEditingShop] = useState<Shop | null>(null);
  const [form] = Form.useForm();

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [mRes, sRes] = await Promise.all([
        merchantService.get(id),
        shopService.listByMerchant(id),
      ]);
      setMerchant(mRes.data);
      setShops(sRes.data);
    } catch {
      message.error("加载数据失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  const openCreateModal = () => {
    setEditingShop(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (shop: Shop) => {
    setEditingShop(shop);
    form.setFieldsValue(shop);
    setModalOpen(true);
  };

  const handleSaveShop = async () => {
    if (!id) return;
    const values = await form.validateFields();
    try {
      if (editingShop) {
        await shopService.update(editingShop.id, values);
        message.success("门店已更新");
      } else {
        await shopService.create(id, values);
        message.success("门店已创建");
      }
      setModalOpen(false);
      fetchData();
    } catch {
      message.error("保存失败");
    }
  };

  const handleDeleteShop = async (sid: string) => {
    try {
      await shopService.delete(sid);
      message.success("门店已删除");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const shopColumns = [
    { title: "门店名称", dataIndex: "name", key: "name" },
    { title: "地址", dataIndex: "address", key: "address", render: (v: string | null) => v || "-" },
    { title: "电话", dataIndex: "phone", key: "phone", render: (v: string | null) => v || "-" },
    { title: "品类", dataIndex: "category", key: "category", render: (v: string | null) => v ? <Tag>{v}</Tag> : "-" },
    {
      title: "状态", dataIndex: "status", key: "status",
      render: (s: string) => <Tag color={s === "active" ? "green" : "default"}>{s === "active" ? "营业中" : "已关闭"}</Tag>,
    },
    {
      title: "操作", key: "actions",
      render: (_: unknown, record: Shop) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEditModal(record)}>编辑</Button>
          <Popconfirm title="确定删除此门店吗？" onConfirm={() => handleDeleteShop(record.id)} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!merchant && loading) return <div>加载中...</div>;
  if (!merchant) return <div>商家不存在</div>;

  return (
    <div>
      <Button
        type="link"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate("/merchants")}
        style={{ padding: 0, marginBottom: 16 }}
      >
        返回商家列表
      </Button>

      <Card style={{ marginBottom: 24 }}>
        <Title level={4}>{merchant.name}</Title>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="联系人">{merchant.contact_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="电话">{merchant.contact_phone || "-"}</Descriptions.Item>
          <Descriptions.Item label="套餐等级">
            <Tag color={merchant.tier === "enterprise" ? "gold" : merchant.tier === "pro" ? "blue" : "default"}>
              {merchant.tier}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="备注">{merchant.notes || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>门店列表</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新建门店</Button>
      </div>

      <Table
        dataSource={shops}
        columns={shopColumns}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      <Modal
        title={editingShop ? "编辑门店" : "新建门店"}
        open={modalOpen}
        onOk={handleSaveShop}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="门店名称" name="name" rules={[{ required: true, message: "请输入门店名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="地址" name="address">
            <Input />
          </Form.Item>
          <Form.Item label="电话" name="phone">
            <Input />
          </Form.Item>
          <Form.Item label="品类" name="category" extra="商圈分析按品类映射高德类型，请选择下列选项之一">
            <Select
              allowClear
              placeholder="选择品类"
              options={[
                { value: "火锅", label: "火锅" },
                { value: "烧烤", label: "烧烤" },
                { value: "快餐", label: "快餐" },
                { value: "咖啡", label: "咖啡" },
                { value: "甜品/烘焙", label: "甜品/烘焙" },
                { value: "日料", label: "日料" },
                { value: "西餐", label: "西餐" },
                { value: "私房菜", label: "私房菜" },
              ]}
            />
          </Form.Item>
          {editingShop && (
            <Form.Item label="状态" name="status">
              <Input />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
