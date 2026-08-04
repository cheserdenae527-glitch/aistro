import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Input,
  Modal,
  Row,
  Select,
  Slider,
  Spin,
  Steps,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ExportOutlined,
  PictureOutlined,
  ThunderboltOutlined,
  ZoomInOutlined,
} from "@ant-design/icons";
import AssetPickerDrawer from "../components/studio/AssetPickerDrawer";
import DeckPreviewModal, { QaBadge } from "../components/studio/DeckPreviewModal";
import { shopService, type Shop } from "../services/shops";
import {
  studioService,
  type DeckCreateResponse,
  type DeckTemplate,
  type StudioCopy,
  type StudioDeck,
} from "../services/studio";
import { type DesignAsset } from "../services/designs";
import { getApiError, showApiError } from "../utils/errors";
import {
  clampPageCount,
  isCopyUsable,
  qaSummary,
  themeOptions,
  validateCopyForm,
  type CopyFormValues,
  type ThemePreset,
} from "../utils/studio";

const { Title, Text } = Typography;
const { TextArea } = Input;

function isStatus(e: unknown, code: number): boolean {
  return (
    !!e &&
    typeof e === "object" &&
    "response" in e &&
    (e as { response?: { status?: number } }).response?.status === code
  );
}

function isRateLimit(e: unknown): boolean {
  if (isStatus(e, 429)) return true;
  const msg = getApiError(e);
  return msg.includes("频繁") || msg.includes("Too Many Requests");
}

function TemplateCard({
  template,
  active,
  palette,
  onClick,
}: {
  template: DeckTemplate;
  active: boolean;
  palette: ThemePreset;
  onClick: () => void;
}) {
  const editorial = template === "editorial";
  return (
    <div
      onClick={onClick}
      style={{
        width: 180,
        border: active ? "2px solid #1677ff" : "2px solid #eee",
        borderRadius: 10,
        overflow: "hidden",
        cursor: "pointer",
        background: palette.paper,
        padding: 0,
      }}
      title={`${editorial ? "Editorial 杂志风" : "Swiss 瑞士风"} · ${palette.label}`}
    >
      <div style={{ height: 90, position: "relative", padding: "12px 14px" }}>
        <div
          style={{
            fontFamily: editorial ? "Georgia, 'Noto Serif SC', serif" : "Arial, sans-serif",
            fontWeight: editorial ? 700 : 300,
            fontSize: 34,
            color: palette.ink,
            lineHeight: 1.1,
          }}
        >
          Aa
        </div>
        <div
          style={{
            marginTop: 6,
            height: 6,
            width: "70%",
            background: editorial ? palette.accent : palette.ink,
            opacity: editorial ? 0.55 : 0.25,
          }}
        />
        <div
          style={{
            position: "absolute",
            right: 14,
            bottom: 12,
            width: 26,
            height: 26,
            background: palette.accent,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 14,
            bottom: 12,
            width: 16,
            height: 16,
            border: `2px solid ${palette.accent}`,
          }}
        />
      </div>
      <div
        style={{
          padding: "6px 10px",
          fontSize: 13,
          background: active ? "#e6f4ff" : "transparent",
          color: active ? "#1677ff" : "#333",
          fontWeight: 600,
        }}
      >
        {editorial ? "Editorial 杂志风" : "Swiss 瑞士风"}
      </div>
    </div>
  );
}

export default function StudioEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const started = useRef(false);

  const [projectTitle, setProjectTitle] = useState("");
  const [shop, setShop] = useState<Shop | null>(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);

  // ---- Step 1 文案 ----
  const [form, setForm] = useState<CopyFormValues>({
    category: "",
    style: "",
    price_range: "",
    topic: "",
    shop_name: "",
  });
  const [generating, setGenerating] = useState(false);
  const [copyCountdown, setCopyCountdown] = useState(0);
  const [copy, setCopy] = useState<StudioCopy | null>(null);
  const [titleTexts, setTitleTexts] = useState<string[]>([]);
  const [selectedTitle, setSelectedTitle] = useState(0);
  const [body, setBody] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  // ---- Step 2 卡组 ----
  const [template, setTemplate] = useState<DeckTemplate>("editorial");
  const [theme, setTheme] = useState("ink-classic");
  const [pageCount, setPageCount] = useState(4);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedAssets, setSelectedAssets] = useState<DesignAsset[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [decking, setDecking] = useState(false);
  const [deckCountdown, setDeckCountdown] = useState(0);
  const [deck, setDeck] = useState<DeckCreateResponse | null>(null);
  const [deckStyle, setDeckStyle] = useState<{ template: DeckTemplate; theme: string } | null>(null);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  // ---- Step 3 导出 ----
  const [exporting, setExporting] = useState(false);

  const applyCopy = useCallback((c: StudioCopy) => {
    setCopy(c);
    setBody(c.body || "");
    setTags(c.tags || []);
    setSelectedTitle(0);
    setTitleTexts((c.titles || []).map((t) => t.text));
    if (c.input_payload) {
      setForm((prev) => ({ ...prev, ...c.input_payload }));
    }
    setStep(1);
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const res = await studioService.getProject(id);
      setProjectTitle(res.data.title);
      const shopRes = await shopService.get(res.data.shop_id);
      setShop(shopRes.data);
      if (res.data.copies.length > 0) {
        const c = res.data.copies[0];
        applyCopy(c);
        if (res.data.decks.length > 0) {
          const d = res.data.decks[0];
          setDeck(toDeckResponse(d));
          setDeckStyle({ template: d.template, theme: d.theme });
          setTemplate(d.template);
          setTheme(d.theme);
          setPageCount(d.page_count);
        }
      }
    } catch (e) {
      showApiError(e);
    } finally {
      setLoading(false);
    }
  }, [id, applyCopy]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, [load]);

  useEffect(() => {
    if (copyCountdown <= 0) return;
    const t = setInterval(() => setCopyCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [copyCountdown]);

  useEffect(() => {
    if (deckCountdown <= 0) return;
    const t = setInterval(() => setDeckCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [deckCountdown]);

  const handleGenerate = async () => {
    const errors = validateCopyForm(form);
    if (errors.length > 0) {
      message.error(errors[0]);
      return;
    }
    setGenerating(true);
    try {
      const res = await studioService.generateCopy(id!, form);
      applyCopy(res.data);
      message.success("文案已生成，可编辑后保存");
    } catch (e) {
      if (isRateLimit(e)) {
        setCopyCountdown(20);
        message.warning("生成过于频繁，请 20 秒后再试");
      } else {
        showApiError(e);
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!copy) return;
    setSaving(true);
    try {
      const titles = (copy.titles || []).map((t, i) => ({
        ...t,
        text: titleTexts[i] ?? t.text,
      }));
      const res = await studioService.updateCopy(copy.id, { titles, body, tags });
      setCopy(res.data);
      setTitleTexts(res.data.titles?.map((t) => t.text) || []);
      message.success("文案已保存");
    } catch (e) {
      showApiError(e);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateDeck = async () => {
    if (!isCopyUsable(copy)) {
      message.warning("还没有文案：请先在 Step 1 填写品类/风格/价格带/主题/店名并点击「生成文案」，保存后再来生成卡组");
      return;
    }
    if (selectedAssets.length + selectedFiles.length === 0) {
      Modal.confirm({
        title: "未选择素材",
        content: "没有素材图时卡组将以纯文字排版，部分页面可能无法通过 QA。是否继续？",
        okText: "继续生成",
        cancelText: "取消",
        onOk: () => runGenerateDeck(),
      });
      return;
    }
    runGenerateDeck();
  };

  const runGenerateDeck = async () => {
    if (decking) return;
    setDecking(true);
    try {
      const payload = {
        copy_id: copy!.id,
        template,
        theme,
        page_count: pageCount,
        asset_ids: selectedAssets.map((a) => a.id),
      };
      const res =
        selectedFiles.length > 0
          ? await studioService.createDeckWithFiles(id!, {
              ...payload,
              files: selectedFiles,
            })
          : await studioService.createDeck(id!, payload);
      setDeck(res.data);
      setDeckStyle({ template, theme });
      if (res.data.status === "failed") {
        message.error(res.data.error_message || "卡组生成失败，请重试");
        return;
      }
      const { allPass, passCount, total } = qaSummary(res.data.qa_report);
      if (allPass) {
        message.success(`卡组已生成，${total} 页 QA 全部通过`);
      } else {
        message.warning(`卡组已生成，但 ${total - passCount} 页未通过 QA，可调整后重试`);
      }
    } catch (e) {
      if (isRateLimit(e)) {
        setDeckCountdown(60);
        message.warning("卡组生成过于频繁，请 60 秒后再试");
      } else if (getApiError(e).includes("timeout") || getApiError(e).includes("aborted")) {
        message.error("生成超时（渲染较慢），请稍后重试或减少页数");
      } else {
        showApiError(e);
      }
    } finally {
      setDecking(false);
    }
  };

  const handleExport = async () => {
    if (!deck) return;
    setExporting(true);
    try {
      const res = await studioService.exportToDesign(deck.deck_id);
      message.success("已导出到视觉设计，正在打开编辑器");
      navigate(`/design/${res.data.design_project_id}`);
    } catch (e) {
      showApiError(e);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const themes = themeOptions(template);
  const qa = qaSummary(deck?.qa_report);
  const usable = isCopyUsable(copy);
  const hasDeck = !!deck && deck.images.length > 0;

  return (
    <div>
      <Title level={4} style={{ marginBottom: 4 }}>
        内容工坊 — {projectTitle}
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        {shop?.name || ""} · 文案 → 卡组 → 导出
      </Text>

      <Steps
        current={step}
        style={{ marginBottom: 24 }}
        items={[
          { title: "文案生成", description: usable ? "已就绪" : "填写素材创作" },
          { title: "卡组渲染", description: hasDeck ? "已生成" : "选模板与素材" },
          { title: "导出", description: "进入视觉设计" },
        ]}
      />

      {/* ============ Step 1 文案 ============ */}
      {step === 0 && (
        <Card title="Step 1 · 生成小红书文案">
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Text strong>品类</Text>
              <Input
                placeholder="如：市井火锅"
                value={form.category}
                maxLength={50}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              />
            </Col>
            <Col span={8}>
              <Text strong>风格</Text>
              <Input
                placeholder="如：烟火气 / 深夜食堂"
                value={form.style}
                maxLength={50}
                onChange={(e) => setForm({ ...form, style: e.target.value })}
              />
            </Col>
            <Col span={8}>
              <Text strong>价格带</Text>
              <Input
                placeholder="如：人均80"
                value={form.price_range}
                maxLength={50}
                onChange={(e) => setForm({ ...form, price_range: e.target.value })}
              />
            </Col>
            <Col span={12}>
              <Text strong>主题</Text>
              <Input
                placeholder="这次想表达什么？"
                value={form.topic}
                maxLength={200}
                onChange={(e) => setForm({ ...form, topic: e.target.value })}
              />
            </Col>
            <Col span={12}>
              <Text strong>店名</Text>
              <Input
                placeholder="门店名称"
                value={form.shop_name}
                maxLength={100}
                onChange={(e) => setForm({ ...form, shop_name: e.target.value })}
              />
            </Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={generating}
              disabled={copyCountdown > 0}
              onClick={handleGenerate}
            >
              {copyCountdown > 0 ? `生成中，请 ${copyCountdown}s 后再试` : "生成文案"}
            </Button>
            <Text type="secondary" style={{ marginLeft: 12 }}>
              基于 11 个内容洞见维度，输出 5 标题 + 正文 + 标签 + 配图指导
            </Text>
          </div>
        </Card>
      )}

      {step === 1 && (
        <div>
          <Card title="Step 1 · 标题 / 正文 / 标签" style={{ marginBottom: 16 }}>
            {!usable ? (
              <Text type="secondary">还没有文案。请在上一步填写表单并点击「生成文案」，得到标题/正文/标签/配图指导后即可继续。</Text>
            ) : (
              <>
                <Text strong>选择标题（5 选 1，可编辑）</Text>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, margin: "10px 0 16px" }}>
                  {(copy?.titles || []).map((t, i) => (
                    <div
                      key={i}
                      onClick={() => setSelectedTitle(i)}
                      style={{
                        border:
                          selectedTitle === i ? "2px solid #1677ff" : "1px solid #d9d9d9",
                        borderRadius: 8,
                        padding: "10px 14px",
                        cursor: "pointer",
                        background: selectedTitle === i ? "#e6f4ff" : "#fff",
                        width: 280,
                      }}
                    >
                      {selectedTitle === i ? (
                        <Input
                          value={titleTexts[i] ?? t.text}
                          maxLength={50}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) =>
                            setTitleTexts((prev) =>
                              prev.map((v, idx) => (idx === i ? e.target.value : v))
                            )
                          }
                        />
                      ) : (
                        <span>{t.text}</span>
                      )}
                      <div style={{ marginTop: 6, fontSize: 12, color: "#999" }}>
                        策略：{t.strategy}
                      </div>
                    </div>
                  ))}
                </div>

                <Text strong>正文（300-800 字）</Text>
                <TextArea
                  rows={10}
                  value={body}
                  maxLength={5000}
                  showCount
                  onChange={(e) => setBody(e.target.value)}
                  style={{ margin: "10px 0 16px" }}
                />

                <Text strong>标签</Text>
                <Select
                  mode="tags"
                  style={{ width: "100%", marginTop: 10 }}
                  placeholder="输入后回车添加标签"
                  value={tags}
                  onChange={(v) => setTags(v as string[])}
                  tokenSeparators={[","]}
                />

                <div style={{ marginTop: 16 }}>
                  <Button type="primary" loading={saving} onClick={handleSave}>
                    保存文案
                  </Button>
                  <Button
                    style={{ marginLeft: 12 }}
                    onClick={() => setStep(2)}
                  >
                    下一步：生成卡组
                  </Button>
                </div>
              </>
            )}
          </Card>

          <Card title="配图指导（来自文案 Agent）">
            {copy?.image_guide ? (
              <div>
                <Text strong>封面主图：</Text>
                <div style={{ margin: "6px 0 12px", color: "#555" }}>
                  {copy.image_guide.cover_prompt}
                </div>
                {copy.image_guide.pages.map((p, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <Tag color="blue">{p.position}</Tag>
                    <Text type="secondary">{p.purpose}</Text>
                    <div style={{ color: "#666", fontSize: 13 }}>{p.prompt}</div>
                  </div>
                ))}
              </div>
            ) : (
              <Text type="secondary">生成文案后自动产出配图指导。</Text>
            )}
          </Card>
        </div>
      )}

      {/* ============ Step 2 卡组 ============ */}
      {step === 2 && (
        <Card title="Step 2 · 生成小红书卡组">
          <Text strong>模板</Text>
          <div style={{ display: "flex", gap: 14, margin: "10px 0 20px" }}>
            <TemplateCard
              template="editorial"
              active={template === "editorial"}
              palette={
                themeOptions("editorial").find((t) => t.key === theme) ||
                themeOptions("editorial")[0]
              }
              onClick={() => {
                setTemplate("editorial");
                if (!themeOptions("editorial").some((t) => t.key === theme)) setTheme("ink-classic");
              }}
            />
            <TemplateCard
              template="swiss"
              active={template === "swiss"}
              palette={
                themeOptions("swiss").find((t) => t.key === theme) ||
                themeOptions("swiss")[0]
              }
              onClick={() => {
                setTemplate("swiss");
                if (!themeOptions("swiss").some((t) => t.key === theme)) setTheme("ikb-blue");
              }}
            />
          </div>

          <Text strong>色板</Text>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, margin: "10px 0 20px" }}>
            {themes.map((t) => (
              <div
                key={t.key}
                onClick={() => setTheme(t.key)}
                style={{
                  width: 96,
                  cursor: "pointer",
                  border: theme === t.key ? "2px solid #1677ff" : "2px solid #eee",
                  borderRadius: 8,
                  overflow: "hidden",
                  background: t.paper,
                }}
                title={t.label}
              >
                <div
                  style={{
                    height: 34,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 13,
                    color: t.ink,
                    fontWeight: 600,
                  }}
                >
                  {t.label}
                </div>
                <div style={{ display: "flex", height: 14 }}>
                  <div style={{ flex: 1, background: t.paper }} />
                  <div style={{ flex: 1, background: t.accent }} />
                </div>
              </div>
            ))}
          </div>

          <Row gutter={24}>
            <Col span={12}>
              <Text strong>页数：{pageCount}</Text>
              <Slider
                min={4}
                max={8}
                value={pageCount}
                onChange={(v) => setPageCount(clampPageCount(v))}
              />
            </Col>
            <Col span={12}>
              <Text strong>素材（{selectedAssets.length + selectedFiles.length}/8）</Text>
              <div style={{ marginTop: 8 }}>
                <Button icon={<PictureOutlined />} onClick={() => setPickerOpen(true)}>
                  选择素材（素材库 / 上传）
                </Button>
                {selectedFiles.length > 0 && (
                  <Tag color="orange" style={{ marginLeft: 8 }}>
                    已上传 {selectedFiles.length} 张
                  </Tag>
                )}
                {selectedAssets.length > 0 && (
                  <Tag color="blue" style={{ marginLeft: 8 }}>
                    已选素材 {selectedAssets.length} 张
                  </Tag>
                )}
              </div>
            </Col>
          </Row>

          <div style={{ marginTop: 20 }}>
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              loading={decking}
              disabled={deckCountdown > 0}
              onClick={handleGenerateDeck}
            >
              {deckCountdown > 0 ? `请 ${deckCountdown}s 后再试` : "生成卡组"}
            </Button>
            <Text type="secondary" style={{ marginLeft: 12 }}>
              渲染 1080×1440 PNG × {pageCount} 页 + 自动 QA，约 10-30 秒
            </Text>
          </div>

          {deck?.error_message && deck.status === "failed" && (
            <div style={{ marginTop: 16, color: "#cf1322" }}>{deck.error_message}</div>
          )}

          {hasDeck && (
            <div style={{ marginTop: 20 }}>
              <Text strong>
                预览（{deck.images.length} 页 · QA {qa.passCount}/{qa.total} 通过
                {qa.allPass ? " ✅" : " ⚠️"})
              </Text>

              {/* 模板 + 色板样式 */}
              {deckStyle && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    flexWrap: "wrap",
                    marginTop: 10,
                    padding: "10px 14px",
                    background: "#fafafa",
                    border: "1px solid #f0f0f0",
                    borderRadius: 8,
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    样式：
                  </Text>
                  <Tag color={deckStyle.template === "swiss" ? "purple" : "geekblue"}>
                    {deckStyle.template === "swiss" ? "Swiss 瑞士风" : "Editorial 杂志风"}
                  </Tag>
                  <Tag>{themeOptions(deckStyle.template).find((t) => t.key === deckStyle.theme)?.label || deckStyle.theme}</Tag>
                  {(() => {
                    const preset = themeOptions(deckStyle.template).find((t) => t.key === deckStyle.theme);
                    if (!preset) return null;
                    return (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        {[preset.paper, preset.accent, preset.ink].map((color, i) => (
                          <span
                            key={i}
                            title={color}
                            style={{
                              display: "inline-block",
                              width: 18,
                              height: 18,
                              borderRadius: 4,
                              background: color,
                              border: "1px solid rgba(0,0,0,.12)",
                            }}
                          />
                        ))}
                      </span>
                    );
                  })()}
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: "auto" }}>
                    点击任意页面可放大查看
                  </Text>
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  gap: 14,
                  overflowX: "auto",
                  padding: "12px 0",
                }}
              >
                {deck.images.map((img) => (
                  <div
                    key={img.page}
                    style={{ flex: "none", width: 216, cursor: "zoom-in" }}
                    onClick={() => setPreviewIndex(img.page - 1)}
                  >
                    <div style={{ position: "relative" }}>
                      <img
                        src={img.url}
                        alt={`第 ${img.page} 页`}
                        style={{
                          width: 216,
                          height: 288,
                          objectFit: "cover",
                          borderRadius: 8,
                          border: "1px solid #eee",
                          background: "#fff",
                          display: "block",
                        }}
                      />
                      <div
                        style={{
                          position: "absolute",
                          right: 8,
                          bottom: 8,
                          background: "rgba(0,0,0,.55)",
                          color: "#fff",
                          borderRadius: 999,
                          padding: "3px 10px",
                          fontSize: 12,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        <ZoomInOutlined /> 放大
                      </div>
                    </div>
                    <div style={{ marginTop: 6, textAlign: "center" }}>
                      <QaBadge qa={deck.qa_report} page={img.page} />
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12 }}>
                <Button type="primary" onClick={() => setStep(3)} disabled={deck.status !== "rendered"}>
                  下一步：导出
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ============ Step 3 导出 ============ */}
      {step === 3 && (
        <Card title="Step 3 · 导出到视觉设计">
          {!hasDeck ? (
            <Text type="secondary">还没有可导出的卡组。</Text>
          ) : (
            <div>
              <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
                把 {deck.images.length} 页卡组写入视觉设计素材库（asset_type=photo, source=studio），
                可在编辑器中继续微调。
              </Text>
              <Button
                type="primary"
                size="large"
                icon={<ExportOutlined />}
                loading={exporting}
                onClick={handleExport}
              >
                导出到视觉设计
              </Button>
              <Button style={{ marginLeft: 12 }} onClick={() => setStep(2)}>
                返回修改
              </Button>
            </div>
          )}
        </Card>
      )}

      <DeckPreviewModal
        open={previewIndex !== null}
        images={deck?.images || []}
        qaReport={deck?.qa_report}
        index={previewIndex ?? 0}
        onClose={() => setPreviewIndex(null)}
        onIndexChange={setPreviewIndex}
      />

      <AssetPickerDrawer
        open={pickerOpen}
        shopId={shop?.id || ""}
        copyId={copy?.id || null}
        imageGuide={copy?.image_guide || null}
        selectedAssets={selectedAssets}
        selectedFiles={selectedFiles}
        onClose={() => setPickerOpen(false)}
        onConfirm={(assets, files) => {
          setSelectedAssets(assets);
          setSelectedFiles(files);
        }}
      />
    </div>
  );
}

function toDeckResponse(d: StudioDeck): DeckCreateResponse {
  return {
    deck_id: d.id,
    images: d.images || [],
    qa_report: d.qa_report,
    status: d.status,
    error_message: d.error_message,
  };
}
