import { useEffect, useState } from "react";
import { Button, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from "antd";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { merchantService, type Merchant } from "../services/merchants";

const { Title } = Typography;

export default function MerchantsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMerchant, setEditingMerchant] = useState<Merchant | null>(null);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchMerchants = async () => {
    setLoading(true);
    try {
      const res = await merchantService.list({ name: search || undefined });
      setMerchants(res.data.items);
    } catch {
      message.error("加载商家列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMerchants();
  }, []);

  const handleSearch = () => {
    fetchMerchants();
  };

  const openCreateModal = () => {
    setEditingMerchant(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (merchant: Merchant) => {
    setEditingMerchant(merchant);
    form.setFieldsValue(merchant);
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editingMerchant) {
        await merchantService.update(editingMerchant.id, values);
        message.success("商家已更新");
      } else {
        await merchantService.create(values);
        message.success("商家已创建");
      }
      setModalOpen(false);
      fetchMerchants();
    } catch {
      message.error("保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await merchantService.delete(id);
      message.success("商家已删除");
      fetchMerchants();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "联系人", dataIndex: "contact_name", key: "contact_name", render: (v: string | null) => v || "-" },
    { title: "电话", dataIndex: "contact_phone", key: "contact_phone", render: (v: string | null) => v || "-" },
    {
      title: "套餐", dataIndex: "tier", key: "tier",
      render: (tier: string) => {
        const colors: Record<string, string> = { trial: "default", pro: "blue", enterprise: "gold" };
        return <Tag color={colors[tier] || "default"}>{tier}</Tag>;
      },
    },
    { title: "创建时间", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? v.slice(0, 10) : "-" },
    {
      title: "操作", key: "actions",
      render: (_: unknown, record: Merchant) => (
        <Space>
          <Button type="link" size="small" onClick={() => navigate(`/merchants/${record.id}`)}>查看</Button>
          <Button type="link" size="small" onClick={() => openEditModal(record)}>编辑</Button>
          <Popconfirm title="确定删除此商家吗？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>商家管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新建商家</Button>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Space>
          <Input
            placeholder="搜索商家名称"
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 280 }}
          />
          <Button onClick={handleSearch}>搜索</Button>
        </Space>
      </div>

      <Table
        dataSource={merchants}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        onRow={(record) => ({
          onClick: () => navigate(`/merchants/${record.id}`),
          style: { cursor: "pointer" },
        })}
      />

      <Modal
        title={editingMerchant ? "编辑商家" : "新建商家"}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: "请输入商家名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="联系人" name="contact_name">
            <Input />
          </Form.Item>
          <Form.Item label="电话" name="contact_phone">
            <Input />
          </Form.Item>
          <Form.Item label="套餐等级" name="tier" initialValue="trial">
            <Select>
              <Select.Option value="trial">试用版</Select.Option>
              <Select.Option value="pro">专业版</Select.Option>
              <Select.Option value="enterprise">企业版</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
