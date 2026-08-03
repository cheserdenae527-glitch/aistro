import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Col,
  ColorPicker,
  Divider,
  Empty,
  Input,
  InputNumber,
  List,
  message,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DownloadOutlined,
  EyeOutlined,
  PlusOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { Color } from "antd/es/color-picker";
import {
  designService,
  type DesignAsset,
  type MenuColorScheme,
  type MenuDesign,
  type MenuType,
} from "../../services/designs";
import { profileService, type ColorSchemePreset } from "../../services/profiles";
import { showApiError } from "../../utils/errors";

const { Text } = Typography;
const SECTIONS = ["招牌", "主食", "小吃", "饮品"];

interface DraftItem {
  asset_id: string;
  section: string;
  sort: number;
  override_name?: string | null;
  override_price?: string | null;
  override_tagline?: string | null;
}

interface DraftMenu {
  menu_type: MenuType;
  template_id: string;
  shop_name: string;
  color_scheme: MenuColorScheme;
  items: DraftItem[];
}

const DEFAULT_SCHEME: MenuColorScheme = {
  primary: "#C93828",
  secondary: "#FFF0EE",
  accent: "#A82015",
  text: "#2A0A08",
  preset_name: "江湖红",
};

function blankDraft(): DraftMenu {
  return {
    menu_type: "xhs",
    template_id: "xhs_menu_01",
    shop_name: "",
    color_scheme: { ...DEFAULT_SCHEME },
    items: [],
  };
}

export default function MenuDesignPanel({
  projectId,
  assets,
}: {
  projectId: string;
  assets: DesignAsset[];
}) {
  const [menus, setMenus] = useState<MenuDesign[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftMenu>(blankDraft);
  const [presets, setPresets] = useState<ColorSchemePreset[]>([]);
  const [renderUrl, setRenderUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);

  const dishAssets = useMemo(
    () => assets.filter((a) => a.asset_type === "dish" && a.status === "active"),
    [assets]
  );
  const activeMenu = menus.find((m) => m.id === activeMenuId) || null;

  const loadMenus = useCallback(async () => {
    try {
      const res = await designService.listMenus(projectId);
      setMenus(res.data);
    } catch (e) {
      showApiError(e);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadMenus();
    profileService
      .getColorSchemes()
      .then((res) => setPresets(res.data))
      .catch(() => {});
  }, [loadMenus]);

  const openMenu = (menu: MenuDesign) => {
    setActiveMenuId(menu.id);
    setRenderUrl(menu.output_url);
    setDraft({
      menu_type: menu.menu_type,
      template_id: menu.template_id,
      shop_name: menu.shop_name || "",
      color_scheme: {
        primary: menu.color_scheme?.primary || DEFAULT_SCHEME.primary,
        secondary: menu.color_scheme?.secondary || DEFAULT_SCHEME.secondary,
        accent: menu.color_scheme?.accent || DEFAULT_SCHEME.accent,
        text: menu.color_scheme?.text || DEFAULT_SCHEME.text,
        preset_name: menu.color_scheme?.preset_name || null,
      },
      items: (menu.items || []).map((item, index) => ({
        asset_id: item.asset_id,
        section: item.section || "招牌",
        sort: item.sort ?? index + 1,
        override_name: item.override_name ?? null,
        override_price: item.override_price ?? null,
        override_tagline: item.override_tagline ?? null,
      })),
    });
  };

  const handleNew = () => {
    setActiveMenuId(null);
    setRenderUrl(null);
    setDraft(blankDraft());
  };

  const toggleItem = (asset: DesignAsset, checked: boolean) => {
    setDraft((d) => {
      if (checked) {
        const exists = d.items.some((i) => i.asset_id === asset.id);
        if (exists) return d;
        return {
          ...d,
          items: [
            ...d.items,
            {
              asset_id: asset.id,
              section: "招牌",
              sort: d.items.length + 1,
              override_name: null,
              override_price: null,
              override_tagline: null,
            },
          ],
        };
      }
      return {
        ...d,
        items: d.items
          .filter((i) => i.asset_id !== asset.id)
          .map((i, index) => ({ ...i, sort: index + 1 })),
      };
    });
  };

  const moveItem = (index: number, direction: -1 | 1) => {
    setDraft((d) => {
      const target = index + direction;
      if (target < 0 || target >= d.items.length) return d;
      const items = [...d.items];
      const [moved] = items.splice(index, 1);
      items.splice(target, 0, moved);
      return { ...d, items: items.map((i, idx) => ({ ...i, sort: idx + 1 })) };
    });
  };

  const updateItem = (assetId: string, patch: Partial<DraftItem>) => {
    setDraft((d) => ({
      ...d,
      items: d.items.map((i) => (i.asset_id === assetId ? { ...i, ...patch } : i)),
    }));
  };

  const handleTemplate = (templateId: string) => {
    setDraft((d) => ({
      ...d,
      template_id: templateId,
      menu_type: templateId === "a4_menu_01" ? "a4" : "xhs",
    }));
  };

  const applyPreset = (preset: ColorSchemePreset) => {
    setDraft((d) => ({
      ...d,
      color_scheme: {
        primary: preset.primary,
        secondary: preset.secondary,
        accent: preset.accent,
        text: preset.text,
        preset_name: preset.name,
      },
    }));
  };

  const updateColor = (key: keyof MenuColorScheme, value: string) => {
    setDraft((d) => ({
      ...d,
      color_scheme: { ...d.color_scheme, [key]: value, preset_name: null },
    }));
  };

  const handleSave = async () => {
    if (draft.items.length === 0) {
      message.warning("请至少勾选一个菜品");
      return;
    }
    setSaving(true);
    const payload = {
      menu_type: draft.menu_type,
      template_id: draft.template_id,
      shop_name: draft.shop_name || null,
      color_scheme: draft.color_scheme,
      items: draft.items,
    };
    try {
      if (activeMenu) {
        const res = await designService.updateMenu(projectId, activeMenu.id, {
          ...payload,
          version: activeMenu.version,
        });
        setActiveMenuId(res.data.id);
      } else {
        const res = await designService.createMenu(projectId, payload);
        setActiveMenuId(res.data.id);
      }
      await loadMenus();
      message.success("菜单已保存");
    } catch (e) {
      showApiError(e);
      await loadMenus();
    } finally {
      setSaving(false);
    }
  };

  const handleRender = async () => {
    if (!activeMenu) return;
    setRendering(true);
    try {
      const res = await designService.renderMenu(
        projectId,
        activeMenu.id,
        activeMenu.version
      );
      setRenderUrl(res.data.output_url);
      await loadMenus();
      message.success("渲染完成");
    } catch (e) {
      if (
        e &&
        typeof e === "object" &&
        "response" in e &&
        (e as { response?: { status?: number } }).response?.status === 409
      ) {
        message.warning("菜单版本已变化，已刷新最新版本，请重新渲染");
        await loadMenus();
      } else {
        showApiError(e);
      }
    } finally {
      setRendering(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Row gutter={16}>
      <Col xs={24} lg={10}>
        <Card
          size="small"
          title="模板与色系"
          extra={
            <Button size="small" icon={<PlusOutlined />} onClick={handleNew}>
              新建菜单
            </Button>
          }
          style={{ marginBottom: 16 }}
        >
          <Text strong style={{ fontSize: 13 }}>模板</Text>
          <Radio.Group
            value={draft.template_id}
            onChange={(e) => handleTemplate(e.target.value)}
            style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}
          >
            <Radio value="xhs_menu_01">
              小红书竖版长图 1242×1660（3:4）
            </Radio>
            <Radio value="a4_menu_01">A4 实体菜单 2480×3508（300dpi）</Radio>
          </Radio.Group>

          <Divider style={{ margin: "14px 0" }} />
          <Text strong style={{ fontSize: 13 }}>店名</Text>
          <Input
            value={draft.shop_name}
            maxLength={100}
            placeholder="菜单上显示的店名"
            style={{ marginTop: 8 }}
            onChange={(e) => setDraft((d) => ({ ...d, shop_name: e.target.value }))}
          />

          <Divider style={{ margin: "14px 0" }} />
          <Text strong style={{ fontSize: 13 }}>色系（8 预设 + 自定义）</Text>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {presets.map((preset) => (
              <Tooltip key={preset.name} title={`${preset.name} · ${preset.description || ""}`}>
                <div
                  onClick={() => applyPreset(preset)}
                  style={{
                    display: "flex",
                    gap: 2,
                    cursor: "pointer",
                    border:
                      draft.color_scheme.preset_name === preset.name
                        ? "2px solid #1677ff"
                        : "2px solid transparent",
                    borderRadius: 6,
                    padding: 2,
                  }}
                >
                  {[preset.primary, preset.secondary, preset.accent, preset.text].map(
                    (color, i) => (
                      <div
                        key={i}
                        style={{
                          width: 20,
                          height: 20,
                          borderRadius: 3,
                          background: color,
                        }}
                      />
                    )
                  )}
                </div>
              </Tooltip>
            ))}
          </div>
          <Space wrap style={{ marginTop: 12 }}>
            {(
              [
                ["primary", "主色"],
                ["secondary", "辅色"],
                ["accent", "点缀"],
                ["text", "文字"],
              ] as [keyof MenuColorScheme, string][]
            ).map(([key, label]) => (
              <Space key={key}>
                <ColorPicker
                  value={draft.color_scheme[key] as string}
                  onChange={(c: Color) => updateColor(key, c.toHexString())}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {label}
                </Text>
              </Space>
            ))}
          </Space>
        </Card>

        <Card size="small" title="已保存菜单">
          <List
            size="small"
            dataSource={menus}
            locale={{ emptyText: "暂无菜单" }}
            renderItem={(menu) => (
              <List.Item
                style={{
                  cursor: "pointer",
                  background: activeMenu?.id === menu.id ? "#e6f4ff" : "transparent",
                  borderRadius: 6,
                }}
                onClick={() => openMenu(menu)}
                actions={[
                  <Button
                    key="render"
                    type="text"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={rendering && activeMenu?.id === menu.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      openMenu(menu);
                      setTimeout(() => handleRender(), 0);
                    }}
                  >
                    渲染
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={menu.shop_name || "未命名菜单"}
                  description={
                    <>
                      <Tag>{menu.template_id}</Tag>
                      <Tag color={menu.status === "rendered" ? "green" : "default"}>
                        v{menu.version} · {menu.status}
                      </Tag>
                    </>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
      </Col>

      <Col xs={24} lg={14}>
        <Card
          size="small"
          title="菜品勾选（仅展示素材库中的菜品）"
          extra={
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存菜单
            </Button>
          }
          style={{ marginBottom: 16 }}
        >
          {dishAssets.length === 0 ? (
            <Empty description="素材库还没有菜品素材，先在「素材与编辑」上传或生成菜品图" />
          ) : (
            <List
              size="small"
              dataSource={dishAssets}
              renderItem={(asset) => {
                const item = draft.items.find((i) => i.asset_id === asset.id);
                return (
                  <List.Item>
                    <Space>
                      <Checkbox
                        checked={!!item}
                        onChange={(e) => toggleItem(asset, e.target.checked)}
                      />
                      <div
                        style={{
                          width: 44,
                          height: 44,
                          borderRadius: 6,
                          background: `url(${
                            asset.processed_url || asset.original_url || ""
                          }) center/cover`,
                          border: "1px solid #eee",
                        }}
                      />
                      <Text style={{ width: 110, fontSize: 13 }}>
                        {asset.dish_name || "未命名菜品"}
                      </Text>
                    </Space>
                    {item && (
                      <Space wrap>
                        <Tooltip title="上移">
                          <Button
                            size="small"
                            type="text"
                            icon={<ArrowUpOutlined />}
                            disabled={
                              draft.items.findIndex((i) => i.asset_id === asset.id) === 0
                            }
                            onClick={() =>
                              moveItem(
                                draft.items.findIndex((i) => i.asset_id === asset.id),
                                -1
                              )
                            }
                          />
                        </Tooltip>
                        <Tooltip title="下移">
                          <Button
                            size="small"
                            type="text"
                            icon={<ArrowDownOutlined />}
                            disabled={
                              draft.items.findIndex((i) => i.asset_id === asset.id) ===
                              draft.items.length - 1
                            }
                            onClick={() =>
                              moveItem(
                                draft.items.findIndex((i) => i.asset_id === asset.id),
                                1
                              )
                            }
                          />
                        </Tooltip>
                        <Select
                          size="small"
                          value={item.section}
                          style={{ width: 86 }}
                          onChange={(section) => updateItem(asset.id, { section })}
                          options={SECTIONS.map((s) => ({ label: s, value: s }))}
                        />
                        <InputNumber
                          size="small"
                          min={1}
                          value={item.sort}
                          style={{ width: 60 }}
                          onChange={(sort) =>
                            updateItem(asset.id, { sort: sort || 1 })
                          }
                        />
                        <Input
                          size="small"
                          placeholder="菜单名覆盖"
                          value={item.override_name || ""}
                          maxLength={200}
                          style={{ width: 120 }}
                          onChange={(e) =>
                            updateItem(asset.id, { override_name: e.target.value })
                          }
                        />
                        <Input
                          size="small"
                          placeholder="价格覆盖"
                          value={item.override_price || ""}
                          style={{ width: 84 }}
                          onChange={(e) =>
                            updateItem(asset.id, { override_price: e.target.value })
                          }
                        />
                      </Space>
                    )}
                  </List.Item>
                );
              }}
            />
          )}
          {draft.items.length > 0 && (
            <Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
              已选 {draft.items.length} 个菜品，渲染时 override 优先于素材库字段
            </Text>
          )}
        </Card>

        <Card
          size="small"
          title="渲染预览与导出"
          extra={
            <Button
              type="primary"
              ghost
              icon={<ThunderboltOutlined />}
              loading={rendering}
              disabled={!activeMenu}
              onClick={handleRender}
            >
              渲染菜单
            </Button>
          }
        >
          {!renderUrl && !activeMenu?.output_url ? (
            <Empty description="保存菜单后点击渲染，预览将显示在这里" />
          ) : (
            <div>
              <div style={{ display: "flex", justifyContent: "center" }}>
                <img
                  src={renderUrl || activeMenu?.output_url || ""}
                  alt="菜单渲染结果"
                  style={{
                    maxWidth: "100%",
                    maxHeight: 560,
                    borderRadius: 8,
                    boxShadow: "0 2px 12px rgba(0,0,0,0.12)",
                  }}
                />
              </div>
              <Divider />
              <Space>
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  href={renderUrl || activeMenu?.output_url || undefined}
                  target="_blank"
                  download
                >
                  导出 PNG
                </Button>
                <Button
                  icon={<EyeOutlined />}
                  href={renderUrl || activeMenu?.output_url || undefined}
                  target="_blank"
                >
                  新窗口查看
                </Button>
              </Space>
            </div>
          )}
        </Card>
      </Col>
    </Row>
  );
}
