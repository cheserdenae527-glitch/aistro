import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Space,
  Modal,
  Popconfirm,
  Select,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  liveService,
  type AvatarStatus,
  type AvatarType,
  type LiveAvatar,
} from "../../services/live";
import { AVATAR_STATUS_COLORS, AVATAR_STATUS_LABELS } from "../../utils/live";
import { showApiError } from "../../utils/errors";

const { Text } = Typography;

const TYPE_OPTIONS: { value: AvatarType; label: string }[] = [
  { value: "image", label: "图片形象" },
  { value: "video", label: "视频驱动" },
];

const TTS_OPTIONS: { value: string; label: string }[] = [
  { value: "edgetts", label: "edgetts（Edge，免费推荐）" },
  { value: "cosyvoice", label: "cosyvoice（高自然度）" },
  { value: "gpt-sovits", label: "gpt-sovits（声音克隆）" },
  { value: "tencent", label: "tencent（腾讯云）" },
  { value: "xtts", label: "xtts" },
  { value: "azuretts", label: "azuretts（Azure）" },
  { value: "doubao", label: "doubao（豆包）" },
  { value: "fishtts", label: "fishtts" },
  { value: "indextts2", label: "indextts2" },
  { value: "qwentts", label: "qwentts（通义）" },
  { value: "omnitts", label: "omnitts" },
];

const AI_STYLE_PRESETS: { label: string; prompt: string }[] = [
  { label: "年轻女性", prompt: "一位年轻女性虚拟主播，正面端坐，表情自然微笑，明亮均匀打光，简洁干净直播间背景，半身构图，专业主播气质" },
  { label: "年轻男性", prompt: "一位年轻男性虚拟主播，正面端坐，表情自然，明亮均匀打光，简洁干净直播间背景，半身构图，专业主播气质" },
  { label: "成熟知性女性", prompt: "一位成熟知性女性主持人，正面端坐，气质优雅，明亮打光，干净背景，半身构图" },
  { label: "阳光活力男性", prompt: "一位阳光活力的男性主播，正面端坐，笑容自然，明亮打光，干净直播间背景，半身构图" },
  { label: "动漫风格", prompt: "一位动漫风格虚拟主播，二次元形象，正面端坐，明亮打光，简洁背景，半身构图" },
];

const STATUS_OPTIONS: { value: AvatarStatus; label: string }[] = [
  { value: "draft", label: "草稿" },
  { value: "ready", label: "就绪" },
  { value: "disabled", label: "停用" },
];

interface AvatarFormValues {
  name: string;
  avatar_type: AvatarType;
  image_url?: string;
  video_url?: string;
  engine_base_url?: string;
  provider?: string;
  voice?: string;
  speed?: number;
  pitch?: number;
  identity?: string;
  tone?: string;
  boundaries?: string;
  forbidden_topics?: string;
  status: AvatarStatus;
}

interface Props {
  /** 当前活跃脚本使用的形象 id（用于高亮提示） */
  currentAvatarId?: string | null;
  onChanged?: () => void;
}

export default function AvatarsTab({ currentAvatarId, onChanged }: Props) {
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [avatars, setAvatars] = useState<LiveAvatar[]>([]);
  const [editing, setEditing] = useState<LiveAvatar | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [generatingAvatarId, setGeneratingAvatarId] = useState<string | null>(null);
  const [avatarProgress, setAvatarProgress] = useState(0);
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiOptions, setAiOptions] = useState<{ url: string; object_name: string }[]>([]);
  const [form] = Form.useForm<AvatarFormValues>();

  const load = useCallback(async () => {
    try {
      const res = await liveService.listAvatars({ page: 1, page_size: 100 });
      setAvatars(res.data.items);
    } catch {
      // 保留空态
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ avatar_type: "image", status: "draft" });
    setModalOpen(true);
  };

  const openEdit = (avatar: LiveAvatar) => {
    setEditing(avatar);
    form.setFieldsValue({
      name: avatar.name,
      avatar_type: avatar.avatar_type,
      image_url: avatar.image_url ?? undefined,
      video_url: avatar.video_url ?? undefined,
      engine_base_url: avatar.engine_base_url ?? undefined,
      provider: avatar.voice_config?.provider ?? undefined,
      voice: avatar.voice_config?.voice ?? undefined,
      speed: avatar.voice_config?.speed ?? undefined,
      pitch: avatar.voice_config?.pitch ?? undefined,
      identity: avatar.persona?.identity as string | undefined,
      tone: avatar.persona?.tone as string | undefined,
      boundaries: avatar.persona?.boundaries as string | undefined,
      forbidden_topics: Array.isArray(avatar.persona?.forbidden_topics)
        ? (avatar.persona?.forbidden_topics as string[]).join("，")
        : undefined,
      status: avatar.status,
    });
    setModalOpen(true);
  };

  const handleUploadImage = async (file: File) => {
    setUploadingImage(true);
    try {
      const res = await liveService.uploadAvatarImage(file);
      form.setFieldValue("image_url", res.data.url);
      message.success("形象图已上传，保存后生效");
    } catch (e) {
      showApiError(e);
    } finally {
      setUploadingImage(false);
    }
    return false; // 阻止 antd 默认上传
  };

  const handleUploadVideo = async (file: File) => {
    setUploadingVideo(true);
    try {
      const res = await liveService.uploadAvatarVideo(file);
      form.setFieldValue("video_url", res.data.url);
      message.success("驱动视频已上传，保存后生效");
    } catch (e) {
      showApiError(e);
    } finally {
      setUploadingVideo(false);
    }
    return false;
  };

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) {
      message.warning("请先填写形象描述或选择一个预设风格");
      return;
    }
    setAiGenerating(true);
    setAiOptions([]);
    try {
      const res = await liveService.aiGenerateImage(aiPrompt.trim());
      setAiOptions(res.data.items);
      if (!res.data.items.length) message.error("AI 未生成出形象，请换个描述重试");
    } catch (e) {
      showApiError(e);
    } finally {
      setAiGenerating(false);
    }
  };

  const handleAiPick = (url: string) => {
    form.setFieldValue("image_url", url);
    message.success("已选用 AI 生成的形象图，保存后生效");
    setAiModalOpen(false);
  };

  const handleSubmit = async () => {
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    const persona: Record<string, unknown> = {};
    if (values.identity) persona.identity = values.identity;
    if (values.tone) persona.tone = values.tone;
    if (values.boundaries) persona.boundaries = values.boundaries;
    if (values.forbidden_topics?.trim()) {
      persona.forbidden_topics = values.forbidden_topics
        .split(/[，,、\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    }
    const payload = {
      name: values.name.trim(),
      avatar_type: values.avatar_type,
      image_url: values.image_url?.trim() || null,
      video_url: values.video_url?.trim() || null,
      engine_base_url: values.engine_base_url?.trim() || null,
      voice_config: {
        provider: values.provider?.trim() || null,
        voice: values.voice?.trim() || null,
        speed: values.speed ?? null,
        pitch: values.pitch ?? null,
      },
      persona: Object.keys(persona).length ? persona : null,
      status: values.status,
    };
    try {
      if (editing) {
        const res = await liveService.updateAvatar(editing.id, payload);
        setAvatars((prev) => prev.map((a) => (a.id === editing.id ? res.data : a)));
        onChanged?.();
        message.success("形象已更新");
      } else {
        const res = await liveService.createAvatar(payload);
        setAvatars((prev) => [...prev, res.data]);
        onChanged?.();
        message.success("形象已创建");
      }
      setModalOpen(false);
    } catch (e) {
      showApiError(e);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateEngineAvatar = async (avatar: LiveAvatar) => {
    if (generatingAvatarId) {
      message.warning("已有形象生成中，请等待完成后再生成下一个");
      return;
    }
    if (!avatar.video_url) {
      message.warning("该形象还没有驱动视频，请先上传/填写驱动视频并保存");
      return;
    }
    if (!avatar.engine_base_url) {
      message.warning("该形象还没有引擎地址，请先在编辑里填写引擎地址并保存");
      return;
    }
    setGeneratingAvatarId(avatar.id);
    setAvatarProgress(0);
    try {
      const res = await liveService.generateEngineAvatar(avatar.id, avatar.engine_base_url);
      message.success("已在引擎创建形象生成任务（1-3 分钟）。生成期间请勿同时在引擎页面开直播/录制，避免显存不足");
      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await liveService.getEngineAvatarStatus(avatar.id);
        setAvatarProgress(st.data.progress);
        if (st.data.status === "completed") {
          message.success(`引擎形象生成完成：${st.data.engine_avatar_id ?? res.data.avatar_id}`);
          await load();
          return;
        }
        if (st.data.status === "failed") {
          message.error(`引擎形象生成失败：${st.data.error_msg || "未知错误"}`);
          return;
        }
      }
      message.warning("生成超时，请在引擎侧查看任务进度");
    } catch (e) {
      showApiError(e);
    } finally {
      setGeneratingAvatarId(null);
      setAvatarProgress(0);
    }
  };

  const handleDelete = async (avatar: LiveAvatar) => {
    try {
      await liveService.deleteAvatar(avatar.id);
      setAvatars((prev) => prev.filter((a) => a.id !== avatar.id));
      onChanged?.();
      message.success("形象已删除");
    } catch (e) {
      showApiError(e);
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
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Text type="secondary">
          数字人形象库为团队级共享（org 维度）：同一账号下所有门店可见，跨账号不可见。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建形象
        </Button>
      </div>

      {avatars.length === 0 ? (
        <Card>
          <Empty description="暂无数字人形象，请先新建">
            <Button type="primary" onClick={openCreate}>
              新建形象
            </Button>
          </Empty>
        </Card>
      ) : (
        <List
          grid={{ gutter: 16, column: 2 }}
          dataSource={avatars}
          renderItem={(avatar) => (
            <List.Item>
              <Card
                title={
                  <Space>
                    <Text strong>{avatar.name}</Text>
                    <Tag color={AVATAR_STATUS_COLORS[avatar.status]}>
                      {AVATAR_STATUS_LABELS[avatar.status] ?? avatar.status}
                    </Tag>
                    {avatar.id === currentAvatarId && <Tag color="gold">当前脚本在用</Tag>}
                  </Space>
                }
                extra={
                  <Space>
                    <Button
                      size="small"
                      icon={<RobotOutlined />}
                      loading={generatingAvatarId === avatar.id}
                      disabled={generatingAvatarId !== null && generatingAvatarId !== avatar.id}
                      onClick={() => handleGenerateEngineAvatar(avatar)}
                    >
                      {generatingAvatarId === avatar.id ? `${avatarProgress}%` : "生成引擎形象"}
                    </Button>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(avatar)}>
                      编辑
                    </Button>
                    <Popconfirm title="确定删除该形象？" onConfirm={() => handleDelete(avatar)}>
                      <Button size="small" danger icon={<DeleteOutlined />}>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                }
              >
                <div style={{ marginBottom: 8 }}>
                  <Tag color="geekblue">
                    {avatar.avatar_type === "image" ? "图片形象" : "视频驱动"}
                  </Tag>
                  {avatar.voice_config?.voice && <Tag>声音：{avatar.voice_config.voice}</Tag>}
                  {avatar.engine_avatar_id && <Tag color="green">引擎形象：{avatar.engine_avatar_id}</Tag>}
                </div>
                {avatar.persona?.identity && (
                  <Text type="secondary">人设：{String(avatar.persona.identity)}</Text>
                )}
              </Card>
            </List.Item>
          )}
        />
      )}

      <Modal
        title="AI 生成数字人形象"
        open={aiModalOpen}
        onCancel={() => setAiModalOpen(false)}
        footer={null}
        width={760}
      >
        <div style={{ marginBottom: 12 }}>
          <Text strong>选择风格（可再自行修改描述）</Text>
          <Space wrap style={{ marginTop: 8 }}>
            {AI_STYLE_PRESETS.map((p) => (
              <Button
                key={p.label}
                size="small"
                onClick={() => setAiPrompt(p.prompt)}
              >
                {p.label}
              </Button>
            ))}
          </Space>
        </div>
        <Input.TextArea
          rows={3}
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="描述你想要的数字人形象，如：一位戴眼镜的知性女讲师，正面端坐，明亮打光，直播间背景，半身构图"
        />
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={aiGenerating}
          onClick={handleAiGenerate}
          style={{ marginTop: 12 }}
        >
          生成形象
        </Button>
        {aiOptions.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 12,
              marginTop: 16,
            }}
          >
            {aiOptions.map((opt, idx) => (
              <div
                key={idx}
                onClick={() => handleAiPick(opt.url)}
                style={{ cursor: "pointer", border: "1px solid #d9d9d9", borderRadius: 8, overflow: "hidden" }}
              >
                <img src={opt.url} alt={`AI 形象 ${idx + 1}`} style={{ width: "100%", display: "block" }} />
                <div style={{ textAlign: "center", padding: 6, fontSize: 12 }}>
                  选用此形象
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>

      <Modal
        title={editing ? `编辑形象 — ${editing.name}` : "新建数字人形象"}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="name" label="形象名称" rules={[{ required: true, message: "请填写名称" }]}>
            <Input placeholder="如：店长小雅" maxLength={100} />
          </Form.Item>
          <Form.Item name="avatar_type" label="驱动类型">
            <Select options={TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="image_url" label="形象图（AI 生成 / 上传图片 / 直链 URL）">
            <Space.Compact style={{ width: "100%" }}>
              <Input placeholder="https://... 或点右侧 AI 生成/上传" />
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => {
                  setAiModalOpen(true);
                  setAiPrompt("");
                  setAiOptions([]);
                }}
              >
                AI 生成
              </Button>
              <Upload
                accept="image/png,image/jpeg,image/webp"
                showUploadList={false}
                beforeUpload={handleUploadImage}
              >
                <Button icon={<UploadOutlined />} loading={uploadingImage}>
                  上传
                </Button>
              </Upload>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="video_url" label="驱动视频（可上传视频或填直链 URL）">
            <Space.Compact style={{ width: "100%" }}>
              <Input placeholder="https://... 或点右侧上传" />
              <Upload
                accept="video/mp4,video/webm,video/quicktime"
                showUploadList={false}
                beforeUpload={handleUploadVideo}
              >
                <Button icon={<UploadOutlined />} loading={uploadingVideo}>
                  上传
                </Button>
              </Upload>
            </Space.Compact>
          </Form.Item>
          <Form.Item
            name="engine_base_url"
            label="引擎地址（生成引擎形象用，需支持 /api/avatar/task 的 LiveTalking 引擎）"
            extra="生成引擎形象 = 用上面的驱动视频在引擎侧抽帧生成 data/avatars/<id>，完成后引擎用 --avatar_id 启动即可"
          >
            <Input placeholder="http://localhost:8010" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Card size="small" title="声音（映射 LiveTalking TTS）" style={{ marginBottom: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Form.Item name="provider" label="TTS 提供方">
                <Select
                  options={TTS_OPTIONS}
                  placeholder="选择 TTS 提供方"
                  allowClear
                  showSearch
                />
              </Form.Item>
              <Form.Item
                name="voice"
                label="音色"
                dependencies={["provider"]}
                style={{ marginBottom: 12 }}
              >
                <Input
                  placeholder={
                    (form.getFieldValue("provider") || "edgetts") === "edgetts"
                      ? "如 zh-CN-XiaoxiaoNeural / zh-CN-YunxiNeural"
                      : "填该 TTS 的音色/模型 ID（按引擎文档）"
                  }
                />
              </Form.Item>
              <Form.Item name="speed" label="语速">
                <InputNumber style={{ width: "100%" }} min={0.5} max={2} step={0.1} />
              </Form.Item>
              <Form.Item name="pitch" label="音调">
                <InputNumber style={{ width: "100%" }} min={-10} max={10} step={1} />
              </Form.Item>
            </div>
          </Card>
          <Card size="small" title="人设（生成脚本时快照）">
            <Form.Item name="identity" label="身份">
              <Input placeholder="如：店长小雅" />
            </Form.Item>
            <Form.Item name="tone" label="语气风格">
              <Input placeholder="如：亲切热情，懂美食" />
            </Form.Item>
            <Form.Item name="boundaries" label="边界（不承诺/不夸大）">
              <Input.TextArea rows={2} placeholder="如：不承诺疗效，不讨论政治宗教" />
            </Form.Item>
            <Form.Item name="forbidden_topics" label="禁区话题（逗号分隔）">
              <Input placeholder="政治，宗教" />
            </Form.Item>
          </Card>
        </Form>
      </Modal>
    </div>
  );
}

