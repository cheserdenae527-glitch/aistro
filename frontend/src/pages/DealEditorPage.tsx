import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import SchemeCard from "../components/deals/SchemeCard";
import {
  dealService,
  type CompetitorDeal,
  type DealCopyUpdate,
  type DealItem,
  type DealItemCategory,
  type DealPlatform,
  type DealProject,
  type DealScheme,
  type DealSchemeCopy,
} from "../services/deals";
import { shopService, type Shop } from "../services/shops";
import {
  buildCopyClipboardText,
  CATEGORY_LABELS,
  copyForPlatform,
  formatPrice,
  PLATFORM_LABELS,
  shouldConfirmRegenerate,
} from "../utils/deals";
import { showApiError } from "../utils/errors";

const { Title, Text } = Typography;
const { TextArea } = Input;


const CATEGORY_OPTIONS: { value: DealItemCategory; label: string }[] = [
  { value: "signature", label: "招牌" },
  { value: "staple", label: "主食" },
  { value: "snack", label: "小吃" },
  { value: "drink", label: "饮品" },
];

const SCHEME_TYPE_ORDER: Record<string, number> = { hook: 0, profit: 1, scenario: 2 };

interface ItemFormState {
  mode: "create" | "edit";
  id?: string;
  name: string;
  category: DealItemCategory;
  cost_price: string;
  sale_price: string;
  is_signature: boolean;
  is_high_margin: boolean;
  image_file: File | null;
}

interface CompFormState {
  mode: "create" | "edit";
  id?: string;
  name: string;
  price: string;
  items_summary: string;
  note: string;
}

const EMPTY_ITEM_FORM: ItemFormState = {
  mode: "create",
  name: "",
  category: "signature",
  cost_price: "",
  sale_price: "",
  is_signature: true,
  is_high_margin: false,
  image_file: null,
};

const EMPTY_COMP_FORM: CompFormState = {
  mode: "create",
  name: "",
  price: "",
  items_summary: "",
  note: "",
};

export default function DealEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [project, setProject] = useState<DealProject | null>(null);
  const [shop, setShop] = useState<Shop | null>(null);
  const [items, setItems] = useState<DealItem[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorDeal[]>([]);
  const [schemes, setSchemes] = useState<DealScheme[]>([]);

  const [itemForm, setItemForm] = useState<ItemFormState>(EMPTY_ITEM_FORM);
  const [compForm, setCompForm] = useState<CompFormState>(EMPTY_COMP_FORM);

  const [generating, setGenerating] = useState(false);
  const [generatingPlatform, setGeneratingPlatform] = useState<DealPlatform | null>(null);
  const [exportingPlatform, setExportingPlatform] = useState<DealPlatform | null>(null);
  const [savingItem, setSavingItem] = useState(false);
  const [savingComp, setSavingComp] = useState(false);

  const [schemeEdit, setSchemeEdit] = useState<DealScheme | null>(null);
  const [schemeDraft, setSchemeDraft] = useState({ title: "", description: "", original_price: "", deal_price: "" });

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const projectRes = await dealService.getProject(id);
      setProject(projectRes.data);
      const [itemsRes, compRes, schemesRes] = await Promise.all([
        dealService.listItems(id, { page: 1, page_size: 100 }),
        dealService.listCompetitors(id, { page: 1, page_size: 100 }),
        dealService.listSchemes(id, true),
      ]);
      setItems(itemsRes.data.items);
      setCompetitors(compRes.data.items);
      setSchemes(schemesRes.data);
      const shopRes = await shopService.get(projectRes.data.shop_id).catch(() => null);
      setShop(shopRes?.data ?? null);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, [load]);

  const updateSchemeCopies = useCallback((schemeId: string, copy: DealSchemeCopy) => {
    setSchemes((prev) =>
      prev.map((s) => {
        if (s.id !== schemeId) return s;
        const others = (s.copies ?? []).filter((c) => c.platform !== copy.platform);
        return { ...s, copies: [...others, copy] };
      })
    );
  }, []);

  // ============================================================
  // 菜品清单
  // ============================================================

  const handleItemSubmit = async () => {
    if (!project) return;
    if (!itemForm.name.trim() || !itemForm.sale_price) {
      message.warning("请填写菜品名称和售价");
      return;
    }
    setSavingItem(true);
    try {
      const payload = {
        name: itemForm.name.trim(),
        category: itemForm.category,
        cost_price: itemForm.cost_price ? Number(itemForm.cost_price) : null,
        sale_price: Number(itemForm.sale_price),
        is_signature: itemForm.is_signature,
        is_high_margin: itemForm.is_high_margin,
      };
      if (itemForm.mode === "create") {
        const res = await dealService.createItem(project.id, payload);
        let updated = res.data;
        if (itemForm.image_file) {
          updated = (
            await dealService.uploadItemImage(project.id, res.data.id, itemForm.image_file)
          ).data;
        }
        setItems((prev) => [...prev, updated]);
        message.success("菜品已添加");
      } else if (itemForm.id) {
        const res = await dealService.updateItem(project.id, itemForm.id, payload);
        let updated = res.data;
        if (itemForm.image_file) {
          updated = (
            await dealService.uploadItemImage(project.id, itemForm.id, itemForm.image_file)
          ).data;
        }
        setItems((prev) => prev.map((it) => (it.id === itemForm.id ? updated : it)));
        message.success("菜品已更新");
      }
      setItemForm(EMPTY_ITEM_FORM);
    } catch (e) {
      showApiError(e);
    } finally {
      setSavingItem(false);
    }
  };

  const handleDeleteItem = async (item: DealItem) => {
    if (!project) return;
    try {
      await dealService.deleteItem(project.id, item.id);
      setItems((prev) => prev.filter((it) => it.id !== item.id));
    } catch (e) {
      showApiError(e);
    }
  };

  const itemColumns: ColumnsType<DealItem> = [
    {
      title: "名称",
      dataIndex: "name",
      render: (v: string, row) => (
        <Space>
          {v}
          {row.is_signature && <Tag color="gold">招牌</Tag>}
          {row.is_high_margin && <Tag color="green">高毛利</Tag>}
        </Space>
      ),
    },
    {
      title: "品类",
      dataIndex: "category",
      width: 90,
      render: (v: string) => CATEGORY_LABELS[v] || v,
    },
    {
      title: "成本",
      dataIndex: "cost_price",
      width: 90,
      render: (v: string | null) => formatPrice(v),
    },
    {
      title: "售价",
      dataIndex: "sale_price",
      width: 90,
      render: (v: string) => formatPrice(v),
    },
    {
      title: "图片",
      dataIndex: "image_url",
      width: 70,
      render: (v: string | null) =>
        v ? <img src={v} alt="" style={{ width: 40, height: 40, objectFit: "cover", borderRadius: 6 }} /> : "-",
    },
    {
      title: "操作",
      key: "actions",
      width: 120,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() =>
              setItemForm({
                mode: "edit",
                id: row.id,
                name: row.name,
                category: row.category,
                cost_price: row.cost_price ?? "",
                sale_price: row.sale_price,
                is_signature: row.is_signature,
                is_high_margin: row.is_high_margin,
                image_file: null,
              })
            }
          />
          <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteItem(row)} />
        </Space>
      ),
    },
  ];

  // ============================================================
  // 竞品参考
  // ============================================================

  const handleCompSubmit = async () => {
    if (!project) return;
    if (!compForm.name.trim() || !compForm.price || !compForm.items_summary.trim()) {
      message.warning("请填写竞品名称、价格和内容");
      return;
    }
    setSavingComp(true);
    try {
      const payload = {
        name: compForm.name.trim(),
        price: Number(compForm.price),
        items_summary: compForm.items_summary.trim(),
        note: compForm.note.trim() || null,
      };
      if (compForm.mode === "create") {
        const res = await dealService.createCompetitor(project.id, payload);
        setCompetitors((prev) => [...prev, res.data]);
        message.success("竞品已添加");
      } else if (compForm.id) {
        const res = await dealService.updateCompetitor(project.id, compForm.id, payload);
        setCompetitors((prev) => prev.map((c) => (c.id === compForm.id ? res.data : c)));
        message.success("竞品已更新");
      }
      setCompForm(EMPTY_COMP_FORM);
    } catch (e) {
      showApiError(e);
    } finally {
      setSavingComp(false);
    }
  };

  const handleDeleteCompetitor = async (comp: CompetitorDeal) => {
    if (!project) return;
    try {
      await dealService.deleteCompetitor(project.id, comp.id);
      setCompetitors((prev) => prev.filter((c) => c.id !== comp.id));
    } catch (e) {
      showApiError(e);
    }
  };

  const compColumns: ColumnsType<CompetitorDeal> = [
    { title: "名称", dataIndex: "name" },
    { title: "价格", dataIndex: "price", width: 90, render: (v: string) => formatPrice(v) },
    { title: "包含内容", dataIndex: "items_summary" },
    { title: "备注", dataIndex: "note", render: (v: string | null) => v || "-" },
    {
      title: "操作",
      key: "actions",
      width: 120,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() =>
              setCompForm({
                mode: "edit",
                id: row.id,
                name: row.name,
                price: row.price,
                items_summary: row.items_summary,
                note: row.note ?? "",
              })
            }
          />
          <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteCompetitor(row)} />
        </Space>
      ),
    },
  ];

  // ============================================================
  // 套餐方案
  // ============================================================

  const doGenerate = async () => {
    if (!project) return;
    setGenerating(true);
    try {
      await dealService.generateSchemes(project.id);
      const res = await dealService.listSchemes(project.id, true);
      setSchemes(res.data);
      message.success("套餐方案已生成");
    } catch (e) {
      showApiError(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateClick = () => {
    if (shouldConfirmRegenerate(schemes)) {
      Modal.confirm({
        title: "重新生成套餐方案",
        content: "重新生成将归档当前方案，已编辑内容不会带入新方案，确定继续？",
        okText: "重新生成",
        cancelText: "取消",
        onOk: doGenerate,
      });
    } else {
      doGenerate();
    }
  };

  const handleGenerateCopy = async (scheme: DealScheme, platform: DealPlatform) => {
    if (!project) return;
    setGeneratingPlatform(platform);
    try {
      const res = await dealService.generateCopy(project.id, scheme.id, platform);
      updateSchemeCopies(scheme.id, res.data);
      message.success(`${PLATFORM_LABELS[platform]}文案已生成`);
    } catch (e) {
      showApiError(e);
    } finally {
      setGeneratingPlatform(null);
    }
  };

  const handlePatchCopy = async (
    scheme: DealScheme,
    copy: DealSchemeCopy,
    data: DealCopyUpdate
  ) => {
    if (!project) return;
    try {
      const res = await dealService.updateCopy(project.id, scheme.id, copy.id, data);
      updateSchemeCopies(scheme.id, res.data);
      message.success("文案已保存");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleExport = async (scheme: DealScheme, platform: DealPlatform) => {
    if (!project) return;
    setExportingPlatform(platform);
    try {
      const res = await dealService.exportToDesign(project.id, scheme.id, platform);
      message.success("已导出到视觉设计，正在打开编辑器");
      navigate(`/design/${res.data.design_project_id}`);
    } catch (e) {
      showApiError(e);
    } finally {
      setExportingPlatform(null);
    }
  };

  const handleCopyText = async (scheme: DealScheme, platform: DealPlatform) => {
    const copy = copyForPlatform(scheme, platform);
    const text = buildCopyClipboardText(copy);
    if (!text) {
      message.warning("该平台文案为空");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      message.success("上线文案已复制到剪贴板");
    } catch {
      message.error("复制失败，请手动复制");
    }
  };

  const openSchemeEdit = (scheme: DealScheme) => {
    setSchemeEdit(scheme);
    setSchemeDraft({
      title: scheme.title,
      description: scheme.description ?? "",
      original_price: scheme.original_price,
      deal_price: scheme.deal_price,
    });
  };

  const handleSaveSchemeEdit = async () => {
    if (!project || !schemeEdit) return;
    if (!schemeDraft.title.trim() || !schemeDraft.deal_price) {
      message.warning("请填写方案标题和团购价");
      return;
    }
    try {
      const res = await dealService.updateScheme(project.id, schemeEdit.id, {
        title: schemeDraft.title.trim(),
        description: schemeDraft.description.trim() || null,
        original_price: Number(schemeDraft.original_price),
        deal_price: Number(schemeDraft.deal_price),
      });
      setSchemes((prev) => prev.map((s) => (s.id === schemeEdit.id ? res.data : s)));
      setSchemeEdit(null);
      message.success("方案已保存（状态 → 已编辑）");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleDeleteScheme = async (scheme: DealScheme) => {
    if (!project) return;
    try {
      await dealService.deleteScheme(project.id, scheme.id);
      setSchemes((prev) => prev.filter((s) => s.id !== scheme.id));
    } catch (e) {
      showApiError(e);
    }
  };

  const activeSchemes = schemes
    .filter((s) => !s.is_archived)
    .sort((a, b) => (SCHEME_TYPE_ORDER[a.scheme_type] ?? 9) - (SCHEME_TYPE_ORDER[b.scheme_type] ?? 9));
  const archivedSchemes = schemes
    .filter((s) => s.is_archived)
    .sort((a, b) => b.generation_batch - a.generation_batch || b.created_at.localeCompare(a.created_at));

  const schemesTab = (
    <div>
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={generating}
          onClick={handleGenerateClick}
        >
          生成套餐方案
        </Button>
        <Text type="secondary">
          {schemes.some((s) => !s.is_archived)
            ? `当前第 ${Math.max(...schemes.filter((s) => !s.is_archived).map((s) => s.generation_batch))} 批方案 · 重新生成将归档现有方案`
            : "AI 生成三款套餐：引流款 / 利润款 / 场景款"}
        </Text>
      </div>

      {activeSchemes.length === 0 && (
        <Card>
          <Empty description="暂无套餐方案，点击「生成套餐方案」开始" />
        </Card>
      )}

      {activeSchemes.map((scheme) => (
        <SchemeCard
          key={scheme.id}
          scheme={scheme}
          generatingPlatform={generatingPlatform}
          exportingPlatform={exportingPlatform}
          onGenerateCopy={(p) => handleGenerateCopy(scheme, p)}
          onPatchCopy={(_p, copy, data) => handlePatchCopy(scheme, copy, data)}
          onExport={(p) => handleExport(scheme, p)}
          onCopyText={(p) => handleCopyText(scheme, p)}
          onEditScheme={() => openSchemeEdit(scheme)}
          onDeleteScheme={() => handleDeleteScheme(scheme)}
        />
      ))}

      {archivedSchemes.length > 0 && (
        <Collapse
          style={{ marginTop: 8 }}
          items={[
            {
              key: "archived",
              label: `历史批次（${archivedSchemes.length} 款，已归档 · 只读）`,
              children: archivedSchemes.map((scheme) => (
                <SchemeCard
                  key={scheme.id}
                  scheme={scheme}
                  readonly
                  generatingPlatform={null}
                  exportingPlatform={null}
                  onGenerateCopy={() => undefined}
                  onPatchCopy={() => undefined}
                  onExport={() => undefined}
                  onCopyText={() => undefined}
                  onEditScheme={() => undefined}
                  onDeleteScheme={() => undefined}
                />
              )),
            },
          ]}
        />
      )}

      <Modal
        title="编辑套餐方案"
        open={!!schemeEdit}
        onOk={handleSaveSchemeEdit}
        onCancel={() => setSchemeEdit(null)}
        okText="保存"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
          <div>
            <Text type="secondary">标题</Text>
            <Input
              value={schemeDraft.title}
              onChange={(e) => setSchemeDraft({ ...schemeDraft, title: e.target.value })}
              maxLength={200}
            />
          </div>
          <div>
            <Text type="secondary">描述</Text>
            <TextArea
              value={schemeDraft.description}
              onChange={(e) => setSchemeDraft({ ...schemeDraft, description: e.target.value })}
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </div>
          <div>
            <Text type="secondary">原价</Text>
            <InputNumber
              style={{ width: "100%" }}
              min={0}
              value={Number(schemeDraft.original_price) || undefined}
              onChange={(v) => setSchemeDraft({ ...schemeDraft, original_price: String(v ?? "") })}
            />
          </div>
          <div>
            <Text type="secondary">团购价</Text>
            <InputNumber
              style={{ width: "100%" }}
              min={0}
              value={Number(schemeDraft.deal_price) || undefined}
              onChange={(v) => setSchemeDraft({ ...schemeDraft, deal_price: String(v ?? "") })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );

  // ============================================================
  // 渲染
  // ============================================================

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (loadError || !project) {
    return (
      <Card>
        <Empty description="项目不存在或无权访问">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/deals")}>
            返回项目列表
          </Button>
        </Empty>
      </Card>
    );
  }

  const itemsTab = (
    <div>
      <Card
        size="small"
        title={itemForm.mode === "create" ? "录入菜品" : `编辑菜品：${itemForm.name || "-"}`}
        style={{ marginBottom: 16 }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <Input
            placeholder="菜品名称"
            style={{ width: 180 }}
            value={itemForm.name}
            onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
            maxLength={200}
          />
          <Select
            style={{ width: 110 }}
            value={itemForm.category}
            onChange={(v) => setItemForm({ ...itemForm, category: v })}
            options={CATEGORY_OPTIONS}
          />
          <InputNumber
            placeholder="成本"
            min={0}
            style={{ width: 110 }}
            value={itemForm.cost_price ? Number(itemForm.cost_price) : undefined}
            onChange={(v) => setItemForm({ ...itemForm, cost_price: String(v ?? "") })}
          />
          <InputNumber
            placeholder="售价"
            min={0}
            style={{ width: 110 }}
            value={itemForm.sale_price ? Number(itemForm.sale_price) : undefined}
            onChange={(v) => setItemForm({ ...itemForm, sale_price: String(v ?? "") })}
          />
          <Space size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>
              招牌
            </Text>
            <Switch
              size="small"
              checked={itemForm.is_signature}
              onChange={(v) => setItemForm({ ...itemForm, is_signature: v })}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              高毛利
            </Text>
            <Switch
              size="small"
              checked={itemForm.is_high_margin}
              onChange={(v) => setItemForm({ ...itemForm, is_high_margin: v })}
            />
          </Space>
          <Upload
            accept="image/png,image/jpeg,image/webp"
            showUploadList={false}
            beforeUpload={(file) => {
              setItemForm({ ...itemForm, image_file: file });
              return false;
            }}
          >
            <Button icon={<UploadOutlined />}>
              {itemForm.image_file ? "已选图片" : "上传图片"}
            </Button>
          </Upload>
          <Button type="primary" loading={savingItem} onClick={handleItemSubmit}>
            {itemForm.mode === "create" ? "添加" : "保存"}
          </Button>
          {itemForm.mode === "edit" && (
            <Button onClick={() => setItemForm(EMPTY_ITEM_FORM)}>取消</Button>
          )}
        </div>
      </Card>
      <Table
        rowKey="id"
        size="small"
        columns={itemColumns}
        dataSource={items}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{ emptyText: "暂无菜品，先录入菜品清单" }}
      />
    </div>
  );

  const competitorsTab = (
    <div>
      <Card
        size="small"
        title={compForm.mode === "create" ? "录入竞品套餐" : `编辑竞品：${compForm.name || "-"}`}
        style={{ marginBottom: 16 }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <Input
            placeholder="竞品套餐名"
            style={{ width: 180 }}
            value={compForm.name}
            onChange={(e) => setCompForm({ ...compForm, name: e.target.value })}
            maxLength={200}
          />
          <InputNumber
            placeholder="售价"
            min={0}
            style={{ width: 110 }}
            value={compForm.price ? Number(compForm.price) : undefined}
            onChange={(v) => setCompForm({ ...compForm, price: String(v ?? "") })}
          />
          <Input
            placeholder="包含内容"
            style={{ width: 240 }}
            value={compForm.items_summary}
            onChange={(e) => setCompForm({ ...compForm, items_summary: e.target.value })}
            maxLength={2000}
          />
          <Input
            placeholder="备注（可选）"
            style={{ width: 160 }}
            value={compForm.note}
            onChange={(e) => setCompForm({ ...compForm, note: e.target.value })}
            maxLength={2000}
          />
          <Button type="primary" loading={savingComp} onClick={handleCompSubmit}>
            {compForm.mode === "create" ? "添加" : "保存"}
          </Button>
          {compForm.mode === "edit" && (
            <Button onClick={() => setCompForm(EMPTY_COMP_FORM)}>取消</Button>
          )}
        </div>
      </Card>
      <Table
        rowKey="id"
        size="small"
        columns={compColumns}
        dataSource={competitors}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{ emptyText: "暂无竞品参考，手动录入竞品套餐" }}
      />
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
        <Title level={4} style={{ margin: 0 }}>
          {project.title}
        </Title>
        <Tag color="geekblue">{PLATFORM_LABELS[project.platform] || project.platform}</Tag>
        {project.price_band && <Tag>{project.price_band}</Tag>}
        <Tag color={project.status === "generated" ? "green" : "default"}>
          {project.status === "generated" ? "已生成方案" : "草稿"}
        </Tag>
        {shop && (
          <Text type="secondary">
            {shop.name}
            {shop.category ? ` · ${shop.category}` : ""}
          </Text>
        )}
      </div>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        菜品清单 / 竞品参考 → AI 生成方案 → 平台文案 → 导出视觉设计
      </Text>

      <Tabs
        defaultActiveKey="items"
        items={[
          { key: "items", label: "菜品清单", children: itemsTab },
          { key: "competitors", label: "竞品参考", children: competitorsTab },
          { key: "schemes", label: "套餐方案", children: schemesTab },
        ]}
      />
    </div>
  );
}

