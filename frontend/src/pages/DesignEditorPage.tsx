import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Divider,
  Input,
  List,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import {
  BgColorsOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  FontSizeOutlined,
  PictureOutlined,
  RedoOutlined,
  RotateRightOutlined,
  SaveOutlined,
  ScissorOutlined,
  ThunderboltOutlined,
  UndoOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import CropModal from "../components/CropModal";
import AiGenerateDrawer from "../components/design/AiGenerateDrawer";
import CandidatesModal from "../components/design/CandidatesModal";
import CanvasPreview from "../components/design/CanvasPreview";
import MenuDesignPanel from "../components/design/MenuDesignPanel";
import {
  designService,
  type AssetCandidate,
  type DesignAsset,
  type DesignProject,
} from "../services/designs";
import {
  clampSlider,
  commit,
  createHistory,
  replace,
  redo,
  serializeSettings,
  undo,
  type EditorSettings,
  type HistoryState,
} from "../utils/editStack";
import { loadImageElement, renderToCanvas } from "../utils/canvasRenderer";
import { showApiError } from "../utils/errors";

const { Text, Title } = Typography;
const { TextArea } = Input;

const FILTER_OPTIONS = [
  { label: "原图", value: "none" },
  { label: "暖食", value: "warm" },
  { label: "日系", value: "japanese" },
  { label: "高饱和", value: "vivid" },
  { label: "黑白", value: "bw" },
] as const;

export default function DesignEditorPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id!;

  const [project, setProject] = useState<DesignProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [assets, setAssets] = useState<DesignAsset[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<DesignAsset | null>(null);
  const [canvasSourceUrl, setCanvasSourceUrl] = useState<string | null>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [history, setHistory] = useState<HistoryState>(() => createHistory());
  const settings = history.present;

  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [cropOpen, setCropOpen] = useState(false);
  const [beautifying, setBeautifying] = useState(false);
  const [saving, setSaving] = useState(false);

  const [placingText, setPlacingText] = useState(false);
  const [textDraft, setTextDraft] = useState("");
  const [textSize, setTextSize] = useState(4);
  const [textColor, setTextColor] = useState("#FFFFFF");

  const [editModal, setEditModal] = useState<{ type: "bg" | "enhance" | "ai"; open: boolean }>({
    type: "bg",
    open: false,
  });
  const [editPrompt, setEditPrompt] = useState("");
  const [promptFocus, setPromptFocus] = useState("提升食欲感");
  const [promptGenerating, setPromptGenerating] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [candidates, setCandidates] = useState<{
    type: "bg" | "enhance" | "ai";
    items: AssetCandidate[];
  } | null>(null);
  const [confirmingAid, setConfirmingAid] = useState<string | null>(null);

  const [metaModal, setMetaModal] = useState(false);
  const [dishName, setDishName] = useState("");
  const [price, setPrice] = useState("");
  const [tagline, setTagline] = useState("");

  const wrapperRef = useRef<HTMLDivElement>(null);
  const textDragRef = useRef<{
    id: string;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const sliderPendingRef = useRef<EditorSettings | null>(null);

  const commitUpdate = useCallback(
    (patch: Partial<EditorSettings>) =>
      setHistory((s) => commit(s, { ...s.present, ...patch })),
    []
  );
  const replaceUpdate = useCallback(
    (patch: Partial<EditorSettings>) =>
      setHistory((s) => replace(s, { ...s.present, ...patch })),
    []
  );

  const loadAssets = useCallback(async () => {
    const res = await designService.listAssets(projectId);
    setAssets(res.data);
    return res.data;
  }, [projectId]);

  useEffect(() => {
    (async () => {
      try {
        const [projectRes, assetList] = await Promise.all([
          designService.getProject(projectId),
          loadAssets(),
        ]);
        setProject(projectRes.data);
        const first = assetList.find((a) => a.status === "active");
        if (first && !selectedAsset) {
          setSelectedAsset(first);
          setCanvasSourceUrl(first.processed_url || first.original_url);
        }
      } catch (e) {
        showApiError(e);
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, loadAssets]);

  const selectAsset = (asset: DesignAsset) => {
    setSelectedAsset(asset);
    setCanvasSourceUrl(asset.processed_url || asset.original_url);
    setHistory(createHistory());
    setNaturalSize(null);
    setCropOpen(false);
    setPlacingText(false);
  };

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (!placingText || !textDraft.trim()) return;
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = clampSlider((e.clientX - rect.left) / rect.width, 0.03, 0.97);
    const y = clampSlider((e.clientY - rect.top) / rect.height, 0.05, 0.95);
    commitUpdate({
      texts: [
        ...settings.texts,
        {
          id: `text_${Date.now()}`,
          text: textDraft.trim(),
          x,
          y,
          size: textSize,
          color: textColor,
        },
      ],
    });
    setTextDraft("");
    setPlacingText(false);
  };

  const handleTextDragStart = (e: React.MouseEvent, label: EditorSettings["texts"][number]) => {
    e.stopPropagation();
    textDragRef.current = {
      id: label.id,
      startX: e.clientX,
      startY: e.clientY,
      originX: label.x,
      originY: label.y,
    };
  };

  const handleTextDragMove = (e: React.MouseEvent) => {
    const drag = textDragRef.current;
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const dx = (e.clientX - drag.startX) / rect.width;
    const dy = (e.clientY - drag.startY) / rect.height;
    replaceUpdate({
      texts: settings.texts.map((t) =>
        t.id === drag.id
          ? {
              ...t,
              x: clampSlider(drag.originX + dx, 0.03, 0.97),
              y: clampSlider(drag.originY + dy, 0.05, 0.95),
            }
          : t
      ),
    });
  };

  const handleSliderChange = (patch: Partial<EditorSettings>) =>
    setHistory((s) => {
      if (!sliderPendingRef.current) sliderPendingRef.current = s.present;
      return replace(s, { ...s.present, ...patch });
    });

  const handleSliderComplete = () => {
    const origin = sliderPendingRef.current;
    sliderPendingRef.current = null;
    if (!origin) return;
    setHistory((s) => {
      if (s.present === origin) return s;
      return { past: [...s.past, origin].slice(-100), present: s.present, future: [] };
    });
  };

  const handleUpload = async (file: File) => {
    try {
      const res = await designService.uploadAsset(projectId, file, { asset_type: "photo" });
      message.success("上传成功");
      const list = await loadAssets();
      const uploaded = list.find((a) => a.id === res.data.id);
      if (uploaded) selectAsset(uploaded);
    } catch (e) {
      showApiError(e);
    }
    return false;
  };

  const handleDeleteAsset = async (asset: DesignAsset) => {
    try {
      await designService.deleteAsset(projectId, asset.id);
      const list = await loadAssets();
      if (selectedAsset?.id === asset.id) {
        setSelectedAsset(null);
        setCanvasSourceUrl(null);
        setHistory(createHistory());
      } else if (!list.some((a) => a.id === selectedAsset?.id)) {
        setSelectedAsset(null);
        setCanvasSourceUrl(null);
      }
      message.success("素材已删除");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleBeautify = async () => {
    if (!selectedAsset) return;
    setBeautifying(true);
    try {
      const res = await designService.beautifyAsset(projectId, selectedAsset.id, {
        mode: "enhance",
      });
      setSelectedAsset(res.data);
      setCanvasSourceUrl(res.data.processed_url || res.data.original_url);
      setHistory(createHistory());
      await loadAssets();
      message.success("一键美化完成");
    } catch (e) {
      showApiError(e);
    } finally {
      setBeautifying(false);
    }
  };

  const handleEditSubmit = async () => {
    if (!selectedAsset || !editPrompt.trim()) return;
    setEditLoading(true);
    try {
      const res =
        editModal.type === "bg"
          ? await designService.bgReplace(projectId, selectedAsset.id, editPrompt.trim())
          : editModal.type === "enhance"
            ? await designService.enhance(projectId, selectedAsset.id, editPrompt.trim())
            : await designService.aiBeautify(
                projectId,
                selectedAsset.id,
                editPrompt.trim() || undefined
              );
      setCandidates({ type: editModal.type, items: res.data.candidates });
      setEditModal({ type: editModal.type, open: false });
      setEditPrompt("");
    } catch (e) {
      showApiError(e);
    } finally {
      setEditLoading(false);
    }
  };

  const handleGeneratePrompt = async () => {
    if (!selectedAsset) return;
    setPromptGenerating(true);
    try {
      const res = await designService.generateBeautifyPrompt(
        projectId,
        selectedAsset.id,
        promptFocus,
        selectedAsset.dish_name
      );
      setEditPrompt(res.data.prompt);
    } catch (e) {
      showApiError(e);
    } finally {
      setPromptGenerating(false);
    }
  };

  const handleConfirmCandidate = async (candidate: AssetCandidate) => {
    if (!selectedAsset || !candidates) return;
    setConfirmingAid(candidate.aid);
    try {
      await designService.confirmAsset(projectId, candidate.aid);
      // 派生候选只替换画布源图，正式素材仍是原 aid
      setCanvasSourceUrl(candidate.url);
      setHistory(createHistory());
      setNaturalSize(null);
      await loadAssets();
      message.success("已应用候选图");
      setCandidates(null);
    } catch (e) {
      showApiError(e);
    } finally {
      setConfirmingAid(null);
    }
  };

  const handleSave = async () => {
    if (!selectedAsset || !canvasSourceUrl) return;
    setSaving(true);
    try {
      const image = await loadImageElement(canvasSourceUrl);
      const canvas = document.createElement("canvas");
      renderToCanvas(canvas, image, settings, { includeTexts: true });
      let dataUrl: string;
      try {
        dataUrl = canvas.toDataURL("image/png");
      } catch {
        message.error("画布被跨域图片污染，请配置 MinIO CORS 后重试");
        return;
      }
      const res = await designService.saveAsset(
        projectId,
        selectedAsset.id,
        dataUrl,
        [serializeSettings(settings)],
        selectedAsset.beauty_config
      );
      setSelectedAsset(res.data);
      setCanvasSourceUrl(res.data.processed_url || res.data.original_url);
      await loadAssets();
      message.success("成品已保存到素材库");
    } catch (e) {
      showApiError(e);
    } finally {
      setSaving(false);
    }
  };

  const openMetaModal = (asset: DesignAsset) => {
    setSelectedAsset(asset);
    setDishName(asset.dish_name || "");
    setPrice(asset.price || "");
    setTagline(asset.tagline || "");
    setMetaModal(true);
  };

  const handleSaveMeta = async () => {
    if (!selectedAsset) return;
    try {
      const res = await designService.updateAsset(projectId, selectedAsset.id, {
        dish_name: dishName || null,
        price: price || null,
        tagline: tagline || null,
      });
      setSelectedAsset(res.data);
      setMetaModal(false);
      await loadAssets();
      message.success("素材信息已更新");
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

  const cropAspect = naturalSize ? naturalSize.w / naturalSize.h : 1;
  const targetScale = naturalSize
    ? Math.min(1, 2048 / Math.max(naturalSize.w, naturalSize.h))
    : 1;
  const targetW = naturalSize ? Math.round(naturalSize.w * targetScale) : 1000;
  const targetH = naturalSize ? Math.round(naturalSize.h * targetScale) : 1000;

  return (
    <div>
      <Title level={4} style={{ marginBottom: 4 }}>
        视觉设计编辑器 — {project?.title || "未命名项目"}
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        所有操作实时预览，保存后写入素材库
      </Text>

      <Tabs
        defaultActiveKey="editor"
        items={[
          {
            key: "editor",
            label: "素材与编辑",
            children: (
              <Row gutter={16}>
        {/* ===== 素材库 ===== */}
        <Col xs={24} lg={6}>
          <Card
            size="small"
            title="素材库"
            extra={
              <Space>
                <Upload accept="image/png,image/jpeg,image/webp" showUploadList={false} beforeUpload={handleUpload}>
                  <Button size="small" icon={<UploadOutlined />}>
                    上传
                  </Button>
                </Upload>
                <Button
                  size="small"
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={() => setAiDrawerOpen(true)}
                >
                  AI 生成
                </Button>
              </Space>
            }
          >
            <List
              dataSource={assets}
              locale={{ emptyText: "暂无素材，先上传或 AI 生成" }}
              renderItem={(asset) => (
                <List.Item
                  style={{
                    cursor: "pointer",
                    background:
                      selectedAsset?.id === asset.id ? "#e6f4ff" : "transparent",
                    borderRadius: 6,
                    padding: "6px 8px",
                  }}
                  onClick={() => selectAsset(asset)}
                  actions={[
                    <Button
                      key="meta"
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        openMetaModal(asset);
                      }}
                    />,
                    <Popconfirm
                      key="delete"
                      title="删除该素材？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDeleteAsset(asset);
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      <div
                        style={{
                          width: 48,
                          height: 48,
                          borderRadius: 6,
                          background: `url(${
                            asset.processed_url || asset.original_url || ""
                          }) center/cover`,
                          border: "1px solid #eee",
                        }}
                      />
                    }
                    title={
                      <Space size={4}>
                        <Text style={{ fontSize: 13 }}>{asset.dish_name || asset.asset_type}</Text>
                        {asset.status !== "active" && <Tag color="orange">{asset.status}</Tag>}
                      </Space>
                    }
                    description={
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {asset.price ? `¥${asset.price}` : asset.asset_type}
                        {asset.tagline ? ` · ${asset.tagline}` : ""}
                      </Text>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* ===== 编辑器 ===== */}
        <Col xs={24} lg={18}>
          <Card size="small" title="工具栏">
            <Space wrap>
              <Tooltip title="撤销">
                <Button
                  icon={<UndoOutlined />}
                  disabled={history.past.length === 0}
                  onClick={() => setHistory((s) => undo(s))}
                >
                  撤销
                </Button>
              </Tooltip>
              <Tooltip title="重做">
                <Button
                  icon={<RedoOutlined />}
                  disabled={history.future.length === 0}
                  onClick={() => setHistory((s) => redo(s))}
                >
                  重做
                </Button>
              </Tooltip>
              <Divider type="vertical" />
              <Tooltip title="裁剪">
                <Button
                  icon={<ScissorOutlined />}
                  disabled={!selectedAsset || !canvasSourceUrl}
                  onClick={() => setCropOpen(true)}
                >
                  裁剪
                </Button>
              </Tooltip>
              <Tooltip title="旋转 90°">
                <Button
                  icon={<RotateRightOutlined />}
                  disabled={!selectedAsset}
                  onClick={() => commitUpdate({ rotation: (settings.rotation + 90) % 360 })}
                >
                  旋转
                </Button>
              </Tooltip>
              <Tooltip title="添加卖点文字（点击画布放置）">
                <Button
                  type={placingText ? "primary" : "default"}
                  icon={<FontSizeOutlined />}
                  disabled={!selectedAsset}
                  onClick={() => setPlacingText((v) => !v)}
                >
                  文字
                </Button>
              </Tooltip>
              <Divider type="vertical" />
              <Button
                icon={<BgColorsOutlined />}
                loading={beautifying}
                disabled={!selectedAsset}
                onClick={handleBeautify}
              >
                一键美化
              </Button>
              <Button
                icon={<PictureOutlined />}
                disabled={!selectedAsset}
                onClick={() => {
                  setEditModal({ type: "bg", open: true });
                  setEditPrompt("");
                }}
              >
                背景替换
              </Button>
              <Button
                icon={<ThunderboltOutlined />}
                disabled={!selectedAsset}
                onClick={() => {
                  setEditModal({ type: "enhance", open: true });
                  setEditPrompt("");
                }}
              >
                菜品增强
              </Button>
              <Button
                icon={<ExperimentOutlined />}
                disabled={!selectedAsset}
                onClick={() => {
                  setEditModal({ type: "ai", open: true });
                  setEditPrompt("");
                }}
              >
                AI 美化
              </Button>
              <Divider type="vertical" />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!selectedAsset || !canvasSourceUrl}
                onClick={handleSave}
              >
                保存成品
              </Button>
            </Space>
          </Card>

          {!selectedAsset ? (
            <Card style={{ marginTop: 16 }}>
              <div style={{ textAlign: "center", padding: 48, color: "#999" }}>
                <PictureOutlined style={{ fontSize: 40 }} />
                <div style={{ marginTop: 8 }}>从左侧选择素材开始编辑</div>
              </div>
            </Card>
          ) : (
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col xs={24} md={16}>
                <Card size="small" title={placingText ? "点击画布放置文字" : "实时预览"}>
                  <div
                    ref={wrapperRef}
                    style={{
                      position: "relative",
                      background:
                        "linear-gradient(45deg,#f0f0f0 25%,transparent 25%),linear-gradient(-45deg,#f0f0f0 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#f0f0f0 75%),linear-gradient(-45deg,transparent 75%,#f0f0f0 75%)",
                      backgroundSize: "16px 16px",
                      backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
                      padding: 12,
                      borderRadius: 8,
                      cursor: placingText ? "crosshair" : "default",
                    }}
                    onClick={handleCanvasClick}
                    onMouseMove={handleTextDragMove}
                    onMouseUp={() => (textDragRef.current = null)}
                    onMouseLeave={() => (textDragRef.current = null)}
                  >
                    {canvasSourceUrl && (
                      <CanvasPreview
                        sourceUrl={canvasSourceUrl}
                        settings={settings}
                        onImageLoad={(w, h) => setNaturalSize({ w, h })}
                      />
                    )}
                    {settings.texts.map((label) => (
                      <div
                        key={label.id}
                        style={{
                          position: "absolute",
                          left: `${label.x * 100}%`,
                          top: `${label.y * 100}%`,
                          width: 16,
                          height: 16,
                          transform: "translate(-50%,-50%)",
                          cursor: "move",
                          zIndex: 3,
                        }}
                        onMouseDown={(e) => handleTextDragStart(e, label)}
                        title={label.text}
                      />
                    ))}
                  </div>
                  {selectedAsset.processed_url && (
                    <div
                      style={{
                        marginTop: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                      }}
                    >
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        Pillow 美化结果对照：
                      </Text>
                      <img
                        src={selectedAsset.processed_url}
                        alt="Pillow 美化结果"
                        style={{ width: 56, height: 42, objectFit: "cover", borderRadius: 4 }}
                      />
                      <Button
                        size="small"
                        onClick={() => {
                          setCanvasSourceUrl(selectedAsset.processed_url || "");
                          setHistory(createHistory());
                          setNaturalSize(null);
                        }}
                      >
                        载入为源图
                      </Button>
                    </div>
                  )}
                </Card>
              </Col>

              <Col xs={24} md={8}>
                <Card size="small" title="调色与滤镜" style={{ marginBottom: 16 }}>
                  <Slider
                    min={50}
                    max={150}
                    value={settings.brightness}
                    onChange={(v) => handleSliderChange({ brightness: v })}
                    onAfterChange={handleSliderComplete}
                    marks={{ 50: "暗", 100: "100", 150: "亮" }}
                    tooltip={{ formatter: (v) => `${v}` }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>亮度</Text>
                  <Slider
                    min={50}
                    max={150}
                    value={settings.contrast}
                    onChange={(v) => handleSliderChange({ contrast: v })}
                    onAfterChange={handleSliderComplete}
                    tooltip={{ formatter: (v) => `${v}` }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>对比度</Text>
                  <Slider
                    min={50}
                    max={150}
                    value={settings.saturation}
                    onChange={(v) => handleSliderChange({ saturation: v })}
                    onAfterChange={handleSliderComplete}
                    tooltip={{ formatter: (v) => `${v}` }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>饱和度</Text>
                  <Slider
                    min={-50}
                    max={50}
                    value={settings.temperature}
                    onChange={(v) => handleSliderChange({ temperature: v })}
                    onAfterChange={handleSliderComplete}
                    marks={{ "-50": "冷", 0: "0", 50: "暖" }}
                    tooltip={{ formatter: (v) => `${v}` }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>色温</Text>
                  <Divider style={{ margin: "12px 0" }} />
                  <Radio.Group
                    value={settings.filter}
                    onChange={(e) => commitUpdate({ filter: e.target.value })}
                    options={FILTER_OPTIONS as unknown as { label: string; value: string }[]}
                    optionType="button"
                    buttonStyle="solid"
                    size="small"
                  />
                </Card>

                <Card size="small" title="卖点文字">
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Input
                      placeholder="输入卖点文字，如：招牌必点"
                      value={textDraft}
                      maxLength={30}
                      onChange={(e) => setTextDraft(e.target.value)}
                      onPressEnter={() => setPlacingText(true)}
                    />
                    <Space wrap>
                      <Text type="secondary" style={{ fontSize: 12 }}>字号</Text>
                      <Slider
                        min={2}
                        max={12}
                        value={textSize}
                        onChange={setTextSize}
                        style={{ width: 120 }}
                      />
                      <Select
                        size="small"
                        value={textColor}
                        onChange={setTextColor}
                        style={{ width: 90 }}
                        options={[
                          { label: "白色", value: "#FFFFFF" },
                          { label: "黑色", value: "#111111" },
                          { label: "暖橙", value: "#E8793A" },
                          { label: "江湖红", value: "#C93828" },
                        ]}
                      />
                      <Button size="small" type={placingText ? "primary" : "default"} onClick={() => setPlacingText((v) => !v)}>
                        放置
                      </Button>
                    </Space>
                    {settings.texts.length > 0 && (
                      <List
                        size="small"
                        dataSource={settings.texts}
                        renderItem={(label) => (
                          <List.Item
                            actions={[
                              <Button
                                key="delete"
                                type="text"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() =>
                                  commitUpdate({
                                    texts: settings.texts.filter((t) => t.id !== label.id),
                                  })
                                }
                              />,
                            ]}
                          >
                            <Text style={{ fontSize: 12 }}>{label.text}</Text>
                          </List.Item>
                        )}
                      />
                    )}
                  </Space>
                </Card>
              </Col>
            </Row>
          )}
        </Col>
              </Row>
            ),
          },
          {
            key: "menu",
            label: "菜单设计",
            children: <MenuDesignPanel projectId={projectId} assets={assets} />,
          },
        ]}
      />

      {/* ===== 弹窗 ===== */}
      <AiGenerateDrawer
        open={aiDrawerOpen}
        projectId={projectId}
        onClose={() => setAiDrawerOpen(false)}
        onConfirm={async (candidate) => {
          await designService.confirmAsset(projectId, candidate.aid);
          const list = await loadAssets();
          const confirmed = list.find((a) => a.id === candidate.aid);
          if (confirmed) {
            setSelectedAsset(confirmed);
            setCanvasSourceUrl(confirmed.processed_url || confirmed.original_url);
            setHistory(createHistory());
            setNaturalSize(null);
          }
        }}
      />

      <CropModal
        open={cropOpen}
        src={canvasSourceUrl}
        title="裁剪素材"
        aspect={cropAspect}
        targetWidth={targetW}
        targetHeight={targetH}
        loading={false}
        onCancel={() => setCropOpen(false)}
        onConfirm={(_dataUrl, rect) => {
          commitUpdate({ crop: rect });
          setCropOpen(false);
        }}
      />

      <Modal
        open={editModal.open}
        title={
          editModal.type === "bg"
            ? "背景替换"
            : editModal.type === "enhance"
              ? "菜品增强"
              : "AI 一键美化"
        }
        onCancel={() => setEditModal({ ...editModal, open: false })}
        onOk={handleEditSubmit}
        okText="生成 4 张候选"
        confirmLoading={editLoading}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          {editModal.type === "ai" && (
            <Space wrap>
              <Select
                size="small"
                value={promptFocus}
                onChange={setPromptFocus}
                style={{ width: 140 }}
                options={[
                  { label: "提升食欲感", value: "提升食欲感" },
                  { label: "暖色氛围", value: "暖色氛围" },
                  { label: "突出食材", value: "突出食材" },
                  { label: "日系干净", value: "日系干净" },
                  { label: "构图留白", value: "构图留白" },
                  { label: "高级质感", value: "高级质感" },
                ]}
              />
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                loading={promptGenerating}
                onClick={handleGeneratePrompt}
              >
                AI 生成提示词
              </Button>
            </Space>
          )}
          <TextArea
            rows={4}
            value={editPrompt}
            maxLength={1000}
            onChange={(e) => setEditPrompt(e.target.value)}
            placeholder={
              editModal.type === "bg"
                ? "描述氛围背景，例如：换成深夜暖光木质餐桌，保留菜品主体"
                : editModal.type === "enhance"
                  ? "描述增强方向，例如：提升食物光泽与质感，构图更饱满"
                  : "填写美化提示词，或点击上方按钮让 AI 按侧重点生成"
            }
          />
        </Space>
      </Modal>

      <CandidatesModal
        open={!!candidates}
        title={
          candidates?.type === "bg"
            ? "选择背景替换候选"
            : candidates?.type === "enhance"
              ? "选择增强候选"
              : "选择 AI 美化候选"
        }
        candidates={candidates?.items || []}
        loading={false}
        confirmingAid={confirmingAid}
        onCancel={() => setCandidates(null)}
        onConfirm={handleConfirmCandidate}
      />

      <Modal
        open={metaModal}
        title="编辑素材信息"
        onCancel={() => setMetaModal(false)}
        onOk={handleSaveMeta}
        okText="保存"
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input
            placeholder="菜品名称"
            value={dishName}
            maxLength={200}
            onChange={(e) => setDishName(e.target.value)}
          />
          <Input
            placeholder="价格"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <Input
            placeholder="卖点"
            value={tagline}
            maxLength={200}
            onChange={(e) => setTagline(e.target.value)}
          />
        </Space>
      </Modal>
    </div>
  );
}
