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
          <Form.Item name="image_url" label="形象图（可上传图片或填直链 URL）">
            <Space.Compact style={{ width: "100%" }}>
              <Input placeholder="https://... 或点右侧上传" />
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

