import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Slider,
  Space,
  Spin,
  Switch,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ApiOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import AvatarsTab from "../components/live/AvatarsTab";
import DanmakuTab from "../components/live/DanmakuTab";
import ScriptTab from "../components/live/ScriptTab";
import SessionsTab from "../components/live/SessionsTab";
import {
  liveService,
  type EngineTestResult,
  type LiveAvatar,
  type LivePlatform,
  type LiveProject,
  type LiveScript,
  type PromoItem,
} from "../services/live";
import { shopService, type Shop } from "../services/shops";
import { activeScript, PLATFORM_LABELS } from "../utils/live";
import { showApiError } from "../utils/errors";

const { Text, Title } = Typography;

function pushStatusLabel(push: { status: string; detail: string }) {
  if (push.status === "ok") return "已推送";
  if (push.status === "skipped") return "已跳过（纯 LiveTalking 无 /admin API）";
  return `失败：${push.detail}`;
}

interface BasicForm {
  platform: LivePlatform;
  goal?: string;
  ai_label_text?: string;
  base_url?: string;
  enabled?: boolean;
  api_key?: string;
}

interface Props {
  // 供测试注入的 onReady（加载完成后回调）
  onReady?: () => void;
}

export default function LiveEditorPage({ onReady }: Props) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [project, setProject] = useState<LiveProject | null>(null);
  const [shop, setShop] = useState<Shop | null>(null);
  const [scripts, setScripts] = useState<LiveScript[]>([]);
  const [avatars, setAvatars] = useState<LiveAvatar[]>([]);
  const [savingBasic, setSavingBasic] = useState(false);
  const [testingEngine, setTestingEngine] = useState(false);
  const [previewHeight, setPreviewHeight] = useState(720);
  const [engineTestResult, setEngineTestResult] = useState<EngineTestResult | null>(null);
  const [basicForm] = Form.useForm<BasicForm>();
  const watchedBaseUrl = Form.useWatch("base_url", basicForm);
  const [promoDraft, setPromoDraft] = useState<PromoItem[]>([]);

  const loadAll = useCallback(async () => {
    if (!id) return;
    try {
      const [projectRes, scriptsRes, avatarsRes] = await Promise.all([
        liveService.getProject(id),
        liveService.listScripts(id, true),
        liveService.listAvatars({ page: 1, page_size: 100 }),
      ]);
      setProject(projectRes.data);
      setScripts(scriptsRes.data);
      setAvatars(avatarsRes.data.items);
      basicForm.setFieldsValue({
        platform: projectRes.data.platform,
        goal: projectRes.data.goal ?? undefined,
        ai_label_text: projectRes.data.ai_label_text ?? undefined,
        base_url: projectRes.data.engine_config?.base_url ?? undefined,
        enabled: projectRes.data.engine_config?.enabled ?? false,
      });
      setPromoDraft(projectRes.data.promo_items ?? []);
      const shopRes = await shopService.get(projectRes.data.shop_id).catch(() => null);
      setShop(shopRes?.data ?? null);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
      onReady?.();
    }
  }, [id, basicForm, onReady]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    loadAll();
  }, [loadAll]);

  const reload = useCallback(async () => {
    if (!id) return;
    try {
      const [scriptsRes, avatarsRes] = await Promise.all([
        liveService.listScripts(id, true),
        liveService.listAvatars({ page: 1, page_size: 100 }),
      ]);
      setScripts(scriptsRes.data);
      setAvatars(avatarsRes.data.items);
    } catch {
      // 忽略
    }
  }, [id]);

  const refreshProject = useCallback(async () => {
    if (!id) return;
    try {
      const res = await liveService.getProject(id);
      setProject(res.data);
    } catch {
      // 忽略（仅刷新引擎配置状态，失败不影响页面）
    }
  }, [id]);

  const active = activeScript(scripts);

  const handleEngineTest = async () => {
    if (!project) return;
    const baseUrl = (basicForm.getFieldValue("base_url") as string | undefined)?.trim();
    if (!baseUrl) {
      message.warning("请先填写引擎管理后台地址（base_url）");
      return;
    }
    setTestingEngine(true);
    setEngineTestResult(null);
    try {
      const res = await liveService.engineTest(project.id, { base_url: baseUrl });
      setEngineTestResult(res.data);
      if (res.data.ok) {
        message.success("连接测试通过：健康检查 + 配置推送成功");
        await refreshProject();
      }
    } catch (e) {
      showApiError(e);
    } finally {
      setTestingEngine(false);
    }
  };

  const handleReleaseEngine = async () => {
    try {
      const res = await liveService.releaseEngine();
      if (res.data.released) message.success("已停止引擎并释放 GPU");
      else message.warning("引擎释放未生效（可能未配置引擎路径）");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleStartEngine = async () => {
    try {
      const res = await liveService.startEngine();
      if (res.data.started) message.success("引擎已启动，约 30 秒后可预览");
      else message.warning("引擎启动失败，请检查引擎配置");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleSaveBasic = async () => {
    if (!project) return;
    let values;
    try {
      values = await basicForm.validateFields();
    } catch {
      return;
    }
    setSavingBasic(true);
    try {
      const res = await liveService.updateProject(project.id, {
        platform: values.platform,
        goal: values.goal?.trim() || null,
        ai_label_text: values.ai_label_text?.trim() || null,
        promo_items: promoDraft.length ? promoDraft : null,
        engine_config: {
          base_url: values.base_url?.trim() || null,
          enabled: values.enabled ?? false,
        },
      });
      setProject(res.data);
      message.success("基本信息已保存");
    } catch (e) {
      showApiError(e);
    } finally {
      setSavingBasic(false);
    }
  };

  const updatePromo = (idx: number, patch: Partial<PromoItem>) => {
    setPromoDraft((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

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
        <Alert type="error" showIcon message="直播项目不存在或无权访问" />
        <Button style={{ marginTop: 12 }} onClick={() => navigate("/live")}>
          返回列表
        </Button>
      </Card>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/live")}>
          返回
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          {project.title}
        </Title>
        <Tag color="geekblue">{PLATFORM_LABELS[project.platform] ?? project.platform}</Tag>
        <Text type="secondary">{shop?.name ?? ""}</Text>
      </div>

      <Tabs
        items={[
          {
            key: "basic",
            label: "基本信息",
            children: (
              <Card>
                <Form form={basicForm} layout="vertical" style={{ maxWidth: 720 }}>
                  <Form.Item name="platform" label="主直播平台">
                    <Select
                      options={[
                        { value: "douyin", label: "抖音" },
                        { value: "xiaohongshu", label: "小红书" },
                        { value: "wechat", label: "视频号" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="goal" label="场次目标">
                    <Input.TextArea rows={2} placeholder="如：提升核销 / 拉新 / 互动" />
                  </Form.Item>
                  <Form.Item name="ai_label_text" label="AI 标识文案（合规必填，开播前确认）">
                    <Input.TextArea rows={2} placeholder="如：本直播间由 AI 数字人出镜，真人运营团队值守" />
                  </Form.Item>

                  <Title level={5}>优惠商品（MVP 手填，后续接团购工坊）</Title>
                  {promoDraft.map((p, idx) => (
                    <div
                      key={idx}
                      style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}
                    >
                      <Input
                        style={{ flex: 2 }}
                        placeholder="商品名"
                        value={p.name}
                        onChange={(e) => updatePromo(idx, { name: e.target.value })}
                      />
                      <InputNumber
                        style={{ width: 110 }}
                        placeholder="现价"
                        value={p.price ?? undefined}
                        onChange={(v) => updatePromo(idx, { price: v ?? undefined })}
                      />
                      <InputNumber
                        style={{ width: 110 }}
                        placeholder="原价"
                        value={p.original_price ?? undefined}
                        onChange={(v) => updatePromo(idx, { original_price: v ?? undefined })}
                      />
                      <Input
                        style={{ flex: 2 }}
                        placeholder="规则/链接"
                        value={p.rules ?? ""}
                        onChange={(e) => updatePromo(idx, { rules: e.target.value })}
                      />
                      <Button
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={() => setPromoDraft((prev) => prev.filter((_, i) => i !== idx))}
                      />
                    </div>
                  ))}
                  <Button
                    size="small"
                    icon={<PlusOutlined />}
                    onClick={() => setPromoDraft((prev) => [...prev, { name: "", price: undefined, original_price: undefined, rules: "" }])}
                  >
                    添加优惠商品
                  </Button>

                  <Title level={5} style={{ marginTop: 20 }}>
                    本地引擎连接配置（L3：连接测试 + 配置推送）
                  </Title>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <Form.Item name="base_url" label="引擎管理后台地址">
                      <Input placeholder="http://localhost:8010" />
                    </Form.Item>
                    <Form.Item name="enabled" label="启用" valuePropName="checked">
                      <Switch checkedChildren="开" unCheckedChildren="关" />
                    </Form.Item>
                  </div>
                  <Space style={{ marginBottom: 8 }}>
                    <Text type="secondary">
                      API Key：{project.engine_config?.api_key_configured ? "已配置（不回传明文）" : "未配置"}
                    </Text>
                    <Text type="secondary">
                      {project.engine_config?.enabled ? "引擎启用" : "引擎未启用"}
                    </Text>
                    {project.engine_config?.last_health_check && (
                      <Text type="secondary">
                        最近健康检查：
                        {new Date(project.engine_config.last_health_check).toLocaleString()}
                      </Text>
                    )}
                    <Form.Item name="api_key" label="更新 API Key（留空保持不变）" style={{ marginBottom: 0 }}>
                      <Input.Password placeholder="留空则保留原值" style={{ width: 280 }} />
                    </Form.Item>
                  </Space>
                  <Space direction="vertical" style={{ marginBottom: 16 }}>
                    <Button
                      icon={<ApiOutlined />}
                      loading={testingEngine}
                      onClick={handleEngineTest}
                      disabled={!project.engine_config?.base_url && !watchedBaseUrl}
                    >
                      连接测试
                    </Button>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      测试将对引擎执行 GET /health 健康检查，并推送 persona / wordlist（digital-human-livestream
                      管理后台）；纯 LiveTalking 无 /admin API 时推送自动跳过。通过后记录最近检查时间。
                    </Text>
                    {engineTestResult && (
                      <div
                        style={{
                          padding: "8px 12px",
                          border: "1px solid #d9d9d9",
                          borderRadius: 6,
                          background: "#fafafa",
                          fontSize: 12,
                          maxWidth: 520,
                        }}
                      >
                        {engineTestResult.health && (
                          <Text style={{ display: "block" }}>
                            健康检查：通过（HTTP {engineTestResult.health.status_code}，约{" "}
                            {engineTestResult.health.latency_ms}ms）
                          </Text>
                        )}
                        {engineTestResult.persona_push && (
                          <Text style={{ display: "block" }}>
                            人设推送：{pushStatusLabel(engineTestResult.persona_push)}
                          </Text>
                        )}
                        {engineTestResult.wordlist_push && (
                          <Text style={{ display: "block" }}>
                            敏感词推送：{pushStatusLabel(engineTestResult.wordlist_push)}
                          </Text>
                        )}
                        {engineTestResult.last_health_check && (
                          <Text type="secondary" style={{ display: "block" }}>
                            最近检查：{new Date(engineTestResult.last_health_check).toLocaleString()}
                          </Text>
                        )}
                      </div>
                    )}
                  </Space>
                  <div>
                    <Button type="primary" icon={<SaveOutlined />} loading={savingBasic} onClick={handleSaveBasic}>
                      保存基本信息
                    </Button>
                  </div>
                </Form>
              </Card>
            ),
          },
          {
            key: "avatars",
            label: "数字人形象",
            children: (
              <AvatarsTab currentAvatarId={active?.avatar_id ?? null} onChanged={reload} />
            ),
          },
          {
            key: "scripts",
            label: "直播脚本",
            children: (
              <ScriptTab projectId={project.id} onChanged={reload} />
            ),
          },
          {
            key: "danmaku",
            label: "弹幕互动",
            children: (
              <DanmakuTab projectId={project.id} activeScript={active} />
            ),
          },
          {
            key: "sessions",
            label: "场次与复盘",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                {project.engine_config?.base_url && project.engine_config?.enabled && (
                  <Card size="small" title="引擎画面预览（本地数字人）">
                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
                      <Button size="small" danger onClick={handleReleaseEngine}>
                        释放 GPU
                      </Button>
                      <Button size="small" onClick={handleStartEngine}>
                        启动引擎
                      </Button>
                      <Text style={{ fontSize: 12, whiteSpace: "nowrap" }}>预览高度</Text>
                      <Slider
                        min={320}
                        max={1100}
                        step={20}
                        value={previewHeight}
                        onChange={setPreviewHeight}
                        style={{ flex: 1, maxWidth: 260, margin: 0 }}
                      />
                      <Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                        {previewHeight}px（视频为 3:4 竖版）
                      </Text>
                    </div>
                    <iframe
                      src={`${project.engine_config.base_url.replace(/\/+$/, "")}/dashboard.html`}
                      title="引擎画面预览"
                      style={{
                        width: "100%",
                        height: previewHeight,
                        border: "1px solid #d9d9d9",
                        borderRadius: 8,
                        background: "#000",
                      }}
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      数字人画面由本地引擎渲染：在预览页点「开始连接」，等状态变为已连接后输入文本
                      即可驱动数字人；推流到平台后的画面在直播伴侣/平台直播间查看（纯 LiveTalking
                      引擎请把页面换成 /index.html）。
                    </Text>
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        画质提示：当前形象输出 576×768（3:4），画质上限由形象素材决定——要更清晰请用
                        引擎 avatar.html 上传更高清视频生成形象；平台推流画质在 OBS 输出设置里调分辨率/码率。
                      </Text>
                    </div>
                  </Card>
                )}
                <SessionsTab
                  projectId={project.id}
                  scripts={scripts}
                  avatars={avatars}
                  aiLabelText={project.ai_label_text ?? ""}
                />
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
