import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Input,
  Progress,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined, HighlightOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  designService,
  type AssetCandidate,
  type DesignAsset,
} from "../../services/designs";
import { studioService, type CopyImageGuide } from "../../services/studio";
import { getApiError, showApiError } from "../../utils/errors";
import { addWithCap, candidateToAsset, toggleSelection } from "../../utils/studio";

const { Text } = Typography;
const { TextArea } = Input;

export const MAX_ASSETS = 8;

type SourceMode = "library" | "upload" | "ai";

function isRateLimit(e: unknown): boolean {
  const msg = getApiError(e);
  return msg.includes("频繁") || msg.includes("Too Many Requests");
}

export default function AssetPickerDrawer({
  open,
  shopId,
  copyId,
  imageGuide,
  selectedAssets,
  selectedFiles,
  onConfirm,
  onClose,
}: {
  open: boolean;
  shopId: string;
  copyId: string | null;
  imageGuide: CopyImageGuide | null;
  selectedAssets: DesignAsset[];
  selectedFiles: File[];
  onConfirm: (assets: DesignAsset[], files: File[]) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<SourceMode>("library");
  const [projects, setProjects] = useState<{ id: string; title: string }[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [assets, setAssets] = useState<DesignAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<DesignAsset[]>([]);
  const [files, setFiles] = useState<File[]>([]);

  // AI 生图
  const [aiPrompt, setAiPrompt] = useState("");
  const [mainIdea, setMainIdea] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [aiCandidates, setAiCandidates] = useState<AssetCandidate[]>([]);
  const [generatingAi, setGeneratingAi] = useState(false);
  const [aiProgress, setAiProgress] = useState<number | null>(null);
  const [aiStage, setAiStage] = useState("");

  // 打开时重置为外部选中状态
  useEffect(() => {
    if (!open) return;
    setPicked(selectedAssets);
    setFiles(selectedFiles);
    setMode("library");
    setAiPrompt(imageGuide?.cover_prompt || "");
    setMainIdea("");
    setAiCandidates([]);
    setAiProgress(null);
    setAiStage("");
    setProjectId(null);
    setAssets([]);
    (async () => {
      try {
        const res = await designService.listProjects(shopId);
        setProjects(res.data);
        if (res.data.length > 0) {
          setProjectId(res.data[0].id);
        }
      } catch {
        // 无设计项目时仅保留上传/AI 入口（AI 会自建项目）
      }
    })();
  }, [open, shopId, selectedAssets, selectedFiles, imageGuide]);

  const loadAssets = useCallback(async (pid: string) => {
    setLoading(true);
    try {
      const res = await designService.listAssets(pid, { status: "active" });
      setAssets(res.data);
    } catch (e) {
      showApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && mode === "library" && projectId) loadAssets(projectId);
  }, [open, mode, projectId, loadAssets]);

  const toggleAsset = (asset: DesignAsset) => {
    setPicked((prev) => {
      const { items, added } = toggleSelection(prev, asset, (a, b) => a.id === b.id, MAX_ASSETS);
      if (!added && prev.length === items.length) {
        message.warning(`最多选择 ${MAX_ASSETS} 张素材`);
      }
      return items;
    });
  };

  const toggleAiCandidate = (c: AssetCandidate) => {
    setPicked((prev) => {
      const asset = candidateToAsset(c, projectId || "");
      const { items, added } = toggleSelection(prev, asset, (a, b) => a.id === b.id, MAX_ASSETS);
      if (!added && prev.length === items.length) {
        message.warning(`最多选择 ${MAX_ASSETS} 张素材`);
      }
      return items;
    });
  };

  const addFiles = (list: File[]) => {
    const { items, overflow } = addWithCap(files, list, MAX_ASSETS - picked.length);
    setFiles(items);
    if (overflow > 0) {
      message.warning(`最多选择 ${MAX_ASSETS} 张素材，已截取前 ${list.length - overflow} 张`);
    }
    return false; // 阻止自动上传
  };

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const runGenerateAi = async (pid: string, prompt: string) => {
    setGeneratingAi(true);
    setAiProgress(0);
    setAiStage("提交生图任务…");
    try {
      const jobRes = await designService.createGenerateJob(pid, prompt);
      const jobId = jobRes.data.job_id;
      const deadline = Date.now() + 10 * 60 * 1000;
      // 轮询 job，实时展示进度
      for (;;) {
        if (Date.now() > deadline) {
          throw new Error("生图超时，请稍后重试");
        }
        const res = await designService.getDesignJob(pid, jobId);
        const job = res.data;
        if (job.status === "success") {
          setAiProgress(100);
          setAiStage("完成");
          const candidates = job.result?.candidates || [];
          setAiCandidates((prev) => [...candidates, ...prev]);
          message.success(`已生成 ${candidates.length} 张候选图，点击缩略图选用`);
          break;
        }
        if (job.status === "failed") {
          throw new Error(job.error || "AI 生图失败，请重试");
        }
        setAiProgress(job.result?.progress ?? null);
        setAiStage(job.result?.stage || "AI 生图中…");
        await sleep(2000);
      }
    } catch (e) {
      if (isRateLimit(e)) {
        setAiProgress(null);
        message.warning("AI 生图过于频繁，请 60 秒后再试");
      } else {
        setAiProgress(null);
        showApiError(e);
      }
    } finally {
      setGeneratingAi(false);
    }
  };

  const handleEnrich = async (text?: string) => {
    const base = (text ?? aiPrompt).trim();
    if (!base) {
      message.warning("请先填写配图方向");
      return;
    }
    if (!copyId) {
      message.warning("还没有文案：配图指导来自文案 Agent。请先在 Step 1 点击「生成文案」，再回来丰富配图提示词");
      return;
    }
    setEnriching(true);
    try {
      const res = await studioService.enrichImagePrompt(copyId, base);
      setAiPrompt(res.data.prompt);
      setMainIdea(res.data.main_idea);
    } catch (e) {
      if (isRateLimit(e)) {
        message.warning("操作过于频繁，请 20 秒后再试");
      } else {
        showApiError(e);
      }
    } finally {
      setEnriching(false);
    }
  };

  const handleGenerateAi = async () => {
    if (!aiPrompt.trim()) {
      message.warning("请输入配图提示词");
      return;
    }
    if (!projectId) {
      try {
        const res = await designService.createProject({
          shop_id: shopId,
          title: "内容工坊素材",
        });
        setProjectId(res.data.id);
        setProjects((prev) => [...prev, { id: res.data.id, title: res.data.title }]);
        await runGenerateAi(res.data.id, aiPrompt.trim());
      } catch (e) {
        showApiError(e);
      }
      return;
    }
    await runGenerateAi(projectId, aiPrompt.trim());
  };

  const confirm = () => {
    if (picked.length + files.length === 0) {
      message.warning("请至少选择或上传 1 张素材");
      return;
    }
    onConfirm(picked, files);
    onClose();
  };

  const total = picked.length + files.length;
  const guidePrompts = [
    ...(imageGuide?.pages || []).map((p) => ({ label: p.position, value: p.prompt })),
  ];

  return (
    <Drawer
      open={open}
      title={`选择卡组素材（${total}/${MAX_ASSETS}）`}
      width={680}
      onClose={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={confirm} disabled={total === 0}>
            确定（{total} 张）
          </Button>
        </Space>
      }
    >
      <Segmented
        block
        value={mode}
        onChange={(v) => setMode(v as SourceMode)}
        options={[
          { label: "素材库", value: "library" },
          { label: "上传图片", value: "upload" },
          { label: "AI 生图", value: "ai" },
        ]}
        style={{ marginBottom: 16 }}
      />

      {/* 已选摘要 */}
      {total > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Tag color="blue">已选素材 {picked.length}</Tag>
          <Tag color="orange">已上传 {files.length}</Tag>
        </div>
      )}

      {mode === "upload" && (
        <div style={{ marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Upload.Dragger
              multiple
              accept="image/png,image/jpeg,image/webp"
              beforeUpload={(file, list) => {
                const badType = !["image/png", "image/jpeg", "image/webp"].includes(file.type);
                if (badType) {
                  message.error(`不支持的文件类型: ${file.name}`);
                  return Upload.LIST_IGNORE;
                }
                if (file.size > 10 * 1024 * 1024) {
                  message.error(`图片超过 10MB: ${file.name}`);
                  return Upload.LIST_IGNORE;
                }
                addFiles(
                  list.filter(
                    (f) =>
                      !!f.type &&
                      ["image/png", "image/jpeg", "image/webp"].includes(f.type) &&
                      f.size <= 10 * 1024 * 1024
                  )
                );
                return false;
              }}
              showUploadList={false}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽上传图片（PNG/JPEG/WebP，≤10MB）</p>
            </Upload.Dragger>
          </Space>

          {files.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Tag color="orange">已上传 {files.length} 张</Tag>
              {files.map((f, i) => (
                <Tag
                  key={`${f.name}-${i}`}
                  closable
                  onClose={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                >
                  {f.name}
                </Tag>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === "library" && (
        <div>
          <div style={{ marginBottom: 12 }}>
            <Select
              style={{ width: "100%" }}
              placeholder="选择视觉设计项目以引用素材"
              value={projectId ?? undefined}
              onChange={(v) => setProjectId(v)}
              options={projects.map((p) => ({ value: p.id, label: p.title }))}
              allowClear
            />
          </div>

          {projectId && (
            <div>
              <Tag color="blue">素材库（{assets.length} 张可用）</Tag>
              {loading ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="加载中…" />
              ) : assets.length === 0 ? (
                <Empty description="该设计项目暂无素材，可切换到上传或 AI 生图" />
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {assets.map((asset) => {
                    const active = picked.some((a) => a.id === asset.id);
                    return (
                      <div
                        key={asset.id}
                        onClick={() => toggleAsset(asset)}
                        style={{
                          width: 96,
                          height: 96,
                          borderRadius: 8,
                          overflow: "hidden",
                          cursor: "pointer",
                          border: active ? "3px solid #1677ff" : "3px solid #eee",
                          position: "relative",
                          background: "#f0f0f0",
                        }}
                        title={asset.dish_name || asset.tagline || "素材"}
                      >
                        {asset.thumb_url || asset.original_url ? (
                          <img
                            src={asset.thumb_url || asset.original_url || ""}
                            alt={asset.dish_name || "素材"}
                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                          />
                        ) : (
                          <div
                            style={{
                              width: "100%",
                              height: "100%",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: 12,
                              color: "#999",
                            }}
                          >
                            {asset.dish_name || "素材"}
                          </div>
                        )}
                        {active && (
                          <div
                            style={{
                              position: "absolute",
                              top: 0,
                              right: 0,
                              background: "#1677ff",
                              color: "#fff",
                              width: 20,
                              height: 20,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: 12,
                            }}
                          >
                            ✓
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {picked.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Text strong>已选素材（{picked.length}）</Text>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {picked.map((a) => (
              <div
                key={a.id}
                style={{
                  position: "relative",
                  width: 72,
                  height: 72,
                  borderRadius: 6,
                  overflow: "hidden",
                  border: "1px solid #eee",
                  background: "#f0f0f0",
                }}
              >
                {a.thumb_url || a.original_url ? (
                  <img
                    src={a.thumb_url || a.original_url || ""}
                    alt="已选素材"
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 11,
                      color: "#999",
                    }}
                  >
                    素材
                  </div>
                )}
                <div
                  onClick={() => setPicked((prev) => prev.filter((x) => x.id !== a.id))}
                  title="移除"
                  style={{
                    position: "absolute",
                    top: 0,
                    right: 0,
                    background: "rgba(0,0,0,.6)",
                    color: "#fff",
                    width: 18,
                    height: 18,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    cursor: "pointer",
                    lineHeight: 1,
                  }}
                >
                  ×
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === "ai" && (
        <div>
          <div style={{ marginBottom: 8 }}>
            <Text strong>配图提示词（可编辑）</Text>
          </div>
          <TextArea
            rows={3}
            value={aiPrompt}
            maxLength={1000}
            placeholder="描述想要的配图方向，例如：深夜暖光下的火锅冒热气、市井烟火氛围、构图留白"
            onChange={(e) => setAiPrompt(e.target.value)}
          />
          {guidePrompts.length > 0 && (
            <div style={{ margin: "10px 0" }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                来自配图指导（点击填充）：
              </Text>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {guidePrompts.map((g, i) => (
                  <Tag
                    key={i}
                    color="blue"
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      setAiPrompt(g.value);
                      handleEnrich(g.value);
                    }}
                  >
                    {g.label || `配图 ${i + 1}`}
                  </Tag>
                ))}
              </div>
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button
              icon={<HighlightOutlined />}
              loading={enriching}
              onClick={() => handleEnrich()}
            >
              丰富提示词
            </Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={generatingAi}
              onClick={handleGenerateAi}
            >
              生成 4 张候选图
            </Button>
          </div>
          <Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 12 }}>
            每次生成 4 张，可多次生成，点击缩略图选用
          </Text>
          {(generatingAi || aiProgress !== null) && (
            <div style={{ marginTop: 12 }}>
              <Progress
                percent={aiProgress ?? undefined}
                status={aiProgress === 100 ? "success" : "active"}
                strokeColor={{ from: "#108ee9", to: "#87d068" }}
              />
              <Text type="secondary" style={{ fontSize: 13 }}>
                {aiStage || "AI 生图中…"}
              </Text>
            </div>
          )}
          {mainIdea && (
            <div
              style={{
                marginTop: 8,
                padding: "8px 12px",
                background: "#fffbe6",
                border: "1px solid #ffe58f",
                borderRadius: 6,
                fontSize: 13,
                color: "#ad6800",
              }}
            >
              核心想法：{mainIdea}
            </div>
          )}

          {aiCandidates.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Tag color="purple">AI 候选（{aiCandidates.length} 张，点击选用）</Tag>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 8 }}>
                {aiCandidates.map((c) => {
                  const active = picked.some((a) => a.id === c.aid);
                  return (
                    <div
                      key={c.aid}
                      onClick={() => toggleAiCandidate(c)}
                      style={{
                        width: 96,
                        height: 96,
                        borderRadius: 8,
                        overflow: "hidden",
                        cursor: "pointer",
                        border: active ? "3px solid #1677ff" : "3px solid #eee",
                        position: "relative",
                        background: "#f0f0f0",
                      }}
                      title={active ? "点击取消选用" : "点击选用"}
                    >
                      <img
                        src={c.thumb_url || c.url}
                        alt="AI 候选"
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                      {active && (
                        <div
                          style={{
                            position: "absolute",
                            top: 0,
                            right: 0,
                            background: "#1677ff",
                            color: "#fff",
                            width: 20,
                            height: 20,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 12,
                          }}
                        >
                          ✓
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
