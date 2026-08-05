import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  liveService,
  type ComplianceItem,
  type ComplianceResult,
  type LiveAvatar,
  type LiveExportBundle,
  type LiveScript,
  type ScriptSegment,
  type ScriptSegmentType,
} from "../../services/live";
import {
  activeScript,
  canExport,
  complianceFailures,
  formatDuration,
  formatDurationShort,
  SCRIPT_STATUS_COLORS,
  SCRIPT_STATUS_LABELS,
  SEGMENT_TYPE_LABELS,
  shouldConfirmRegenerate,
  totalDuration,
} from "../../utils/live";
import { showApiError } from "../../utils/errors";
import ExportBundleModal from "./ExportBundleModal";

const { Text } = Typography;

const TONE_OPTIONS = [
  { value: "烟火气", label: "烟火气" },
  { value: "专业", label: "专业" },
  { value: "热情", label: "热情" },
  { value: "治愈", label: "治愈" },
];

interface Props {
  projectId: string;
  onAvatarChanged?: (avatarId: string | null) => void;
  onChanged?: () => void;
}

export default function ScriptTab({ projectId, onAvatarChanged, onChanged }: Props) {
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [scripts, setScripts] = useState<LiveScript[]>([]);
  const [avatars, setAvatars] = useState<LiveAvatar[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [genOpen, setGenOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genForm] = Form.useForm<{ avatar_id: string; tone?: string; duration_min?: number }>();

  const [draft, setDraft] = useState<LiveScript | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const [compliance, setCompliance] = useState<ComplianceResult | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [exportBundle, setExportBundle] = useState<LiveExportBundle | null>(null);

  const load = useCallback(async () => {
    try {
      const [scriptsRes, avatarsRes] = await Promise.all([
        liveService.listScripts(projectId, true),
        liveService.listAvatars({ page: 1, page_size: 100 }),
      ]);
      setScripts(scriptsRes.data);
      setAvatars(avatarsRes.data.items);
    } catch {
      // 保留空态
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, [load]);

  const active = activeScript(scripts);
  const selected =
    scripts.find((s) => s.id === selectedId) ?? active ?? null;

  // 选中脚本变化 → 重置编辑草稿与合规结果
  useEffect(() => {
    setCompliance(null);
    setDraft(selected ? JSON.parse(JSON.stringify(selected)) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id]);

  useEffect(() => {
    onAvatarChanged?.(active?.avatar_id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.avatar_id]);

  const openGenerate = () => {
    if (shouldConfirmRegenerate(scripts)) {
      Modal.confirm({
        title: "重新生成脚本",
        content: "生成新批次会将当前脚本批次归档（已定稿的同样归档），确定继续？",
        okText: "归档并生成",
        cancelText: "取消",
        onOk: () => openGenModal(),
      });
    } else {
      openGenModal();
    }
  };

  const openGenModal = async () => {
    try {
      const res = await liveService.listAvatars({ page: 1, page_size: 100 });
      setAvatars(res.data.items);
    } catch {
      // 忽略，沿用已有列表
    }
    genForm.resetFields();
    const defaultAvatar =
      active?.avatar_id ??
      avatars.find((a) => a.status === "ready")?.id ??
      avatars[0]?.id;
    genForm.setFieldsValue({
      avatar_id: defaultAvatar,
      tone: active?.tone ?? "烟火气",
      duration_min: active ? Math.round((active.total_duration_sec ?? 1800) / 60) : 30,
    });
    setGenOpen(true);
  };

  const handleGenerate = async () => {
    let values;
    try {
      values = await genForm.validateFields();
    } catch {
      return;
    }
    setGenerating(true);
    try {
      const res = await liveService.generateScript(projectId, {
        avatar_id: values.avatar_id,
        tone: values.tone ?? null,
        duration_min: values.duration_min ?? null,
      });
      const list = await liveService.listScripts(projectId, true);
      setScripts(list.data);
      setSelectedId(res.data.id);
      onChanged?.();
      message.success("脚本已生成");
      setGenOpen(false);
    } catch (e) {
      showApiError(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!draft || !selected) return;
    setSavingEdit(true);
    try {
      const content = (draft.content ?? []).map((s) => ({
        type: s.type,
        title: s.title,
        text: s.text,
        duration_sec: s.duration_sec,
        cue: s.cue ?? null,
      }));
      const res = await liveService.updateScript(projectId, selected.id, {
        title: draft.title,
        tone: draft.tone ?? null,
        content,
        total_duration_sec: content.reduce((sum, s) => sum + (s.duration_sec || 0), 0),
      });
      setScripts((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setDraft(JSON.parse(JSON.stringify(res.data)));
      setCompliance(null);
      onChanged?.();
      message.success("脚本微调已保存（状态：已编辑）");
    } catch (e) {
      showApiError(e);
    } finally {
      setSavingEdit(false);
    }
  };

  const updateSegment = (index: number, patch: Partial<ScriptSegment>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const content = [...(prev.content ?? [])];
      content[index] = { ...content[index], ...patch };
      return { ...prev, content };
    });
  };

  const handleComplianceCheck = async () => {
    if (!selected) return;
    try {
      const res = await liveService.complianceCheck(projectId, selected.id);
      setCompliance(res.data);
    } catch (e) {
      showApiError(e);
    }
  };

  const handleConfirm = async () => {
    if (!selected) return;
    setConfirming(true);
    try {
      const res = await liveService.confirmScript(projectId, selected.id);
      setScripts((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setCompliance(res.data.compliance);
      onChanged?.();
      message.success("脚本已定稿");
    } catch (e) {
      // 422 附 items → 直接展示合规失败项
      const err = e as {
        response?: { data?: { detail?: { items?: ComplianceItem[]; message?: string } } };
      };
      const detail = err.response?.data?.detail;
      if (detail?.items) {
        setCompliance({ pass: false, items: detail.items });
        message.error(detail.message || "合规自检未通过");
      } else {
        showApiError(e);
      }
    } finally {
      setConfirming(false);
    }
  };

  const handleExport = async () => {
    if (!selected) return;
    try {
      const res = await liveService.exportScript(projectId, selected.id);
      setExportBundle(res.data);
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

  const failures = complianceFailures(compliance?.items);
  const editable = !!selected && selected.status !== "confirmed";

  const exportDisabledReason = selected
    ? selected.is_archived
      ? "该脚本已归档，如需留档请通过 GET 查看，不支持导出开播包"
      : selected.status !== "confirmed"
        ? "脚本未定稿，无法导出开播包"
        : null
    : "暂无脚本";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <Select
          style={{ width: 320 }}
          value={selected?.id}
          onChange={(v) => setSelectedId(v)}
          placeholder="选择脚本批次"
          options={scripts.map((s) => ({
            value: s.id,
            label: `批次 ${s.generation_batch} · ${s.title}${s.is_archived ? "（已归档）" : ""}`,
          }))}
        />
        <Button type="primary" icon={<ThunderboltOutlined />} onClick={openGenerate}>
          生成脚本
        </Button>
        <Button icon={<FileSearchOutlined />} onClick={handleComplianceCheck} disabled={!selected}>
          合规自检
        </Button>
        <Button
          type="primary"
          ghost
          onClick={handleConfirm}
          loading={confirming}
          disabled={!selected || (compliance !== null && !compliance.pass)}
        >
          定稿
        </Button>
        <Tooltip title={exportDisabledReason}>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleExport}
            disabled={!canExport(selected)}
          >
            导出开播包
          </Button>
        </Tooltip>
      </div>

      {!selected && (
        <Card>
          <Empty description="暂无直播脚本，点击「生成脚本」创建">
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={openGenerate}>
              生成脚本
            </Button>
          </Empty>
        </Card>
      )}

      {selected && (
        <>
          {selected.is_archived && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="当前查看的是已归档批次"
              description="重新生成后旧批次归档保留，仅供查看；已归档脚本不支持导出开播包。"
            />
          )}
          {compliance !== null && !compliance.pass && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 12 }}
              message="合规自检未通过"
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {failures.map((i) => (
                    <li key={i.key}>{i.detail}</li>
                  ))}
                </ul>
              }
            />
          )}

          <Card
            size="small"
            title={
              <Space>
                <Text strong>脚本微调</Text>
                <Tag color={SCRIPT_STATUS_COLORS[selected.status]}>
                  {SCRIPT_STATUS_LABELS[selected.status]}
                </Tag>
                <Tag>总时长 {formatDuration(totalDuration(draft ?? selected))}</Tag>
              </Space>
            }
            extra={
              editable ? (
                <Button
                  size="small"
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={handleSaveEdit}
                  loading={savingEdit}
                >
                  保存微调
                </Button>
              ) : (
                <Tag color="green">已定稿禁止修改</Tag>
              )
            }
          >
            {editable ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 2 }}>
                    <Text type="secondary">标题</Text>
                    <Input
                      value={draft?.title ?? ""}
                      maxLength={200}
                      onChange={(e) =>
                        setDraft((prev) => (prev ? { ...prev, title: e.target.value } : prev))
                      }
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <Text type="secondary">风格</Text>
                    <Select
                      style={{ width: "100%" }}
                      value={draft?.tone ?? undefined}
                      options={TONE_OPTIONS}
                      onChange={(v) =>
                        setDraft((prev) => (prev ? { ...prev, tone: v } : prev))
                      }
                    />
                  </div>
                </div>
                {(draft?.content ?? []).map((seg, idx) => (
                  <Card key={idx} size="small" style={{ borderLeft: "3px solid #1677ff" }}>
                    <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
                      <Tag color="geekblue">
                        {SEGMENT_TYPE_LABELS[seg.type as ScriptSegmentType] ?? seg.type}
                      </Tag>
                      <Input
                        style={{ flex: 1 }}
                        value={seg.title}
                        maxLength={200}
                        onChange={(e) => updateSegment(idx, { title: e.target.value })}
                      />
                      <InputNumber
                        min={1}
                        max={3600}
                        value={seg.duration_sec}
                        addonAfter="s"
                        onChange={(v) => updateSegment(idx, { duration_sec: Number(v ?? 0) })}
                      />
                    </div>
                    <Input.TextArea
                      rows={3}
                      value={seg.text}
                      maxLength={10000}
                      onChange={(e) => updateSegment(idx, { text: e.target.value })}
                    />
                    <div style={{ marginTop: 8 }}>
                      <Input
                        addonBefore="画面/动作提示"
                        value={seg.cue ?? ""}
                        maxLength={500}
                        onChange={(e) => updateSegment(idx, { cue: e.target.value })}
                      />
                    </div>
                  </Card>
                ))}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {(selected.content ?? []).map((seg, idx) => (
                  <Card key={idx} size="small" style={{ borderLeft: "3px solid #52c41a" }}>
                    <div style={{ display: "flex", gap: 12, marginBottom: 8, alignItems: "center" }}>
                      <Tag color="geekblue">
                        {SEGMENT_TYPE_LABELS[seg.type as ScriptSegmentType] ?? seg.type}
                      </Tag>
                      <Text strong>{seg.title}</Text>
                      <Text type="secondary">{formatDurationShort(seg.duration_sec)}</Text>
                    </div>
                    <Text style={{ whiteSpace: "pre-wrap" }}>{seg.text}</Text>
                    {seg.cue && (
                      <div style={{ marginTop: 8 }}>
                        <Text type="secondary">[画面/动作提示] {seg.cue}</Text>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </Card>

          {compliance && (
            <Card size="small" title="合规自检结果" style={{ marginTop: 12 }}>
              {compliance.pass ? (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                  message="合规自检通过，可定稿"
                />
              ) : (
                <div>
                  {compliance.items.map((i) => (
                    <div key={i.key} style={{ marginBottom: 6 }}>
                      {i.ok ? (
                        <CheckCircleOutlined style={{ color: "#52c41a", marginRight: 6 }} />
                      ) : (
                        <ExclamationCircleOutlined style={{ color: "#ff4d4f", marginRight: 6 }} />
                      )}
                      <Text type={i.ok ? "secondary" : undefined}>{i.detail}</Text>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </>
      )}

      <Modal
        title="生成直播脚本"
        open={genOpen}
        onOk={handleGenerate}
        confirmLoading={generating}
        onCancel={() => setGenOpen(false)}
        okText="开始生成"
      >
        <Form form={genForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            name="avatar_id"
            label="数字人形象"
            rules={[{ required: true, message: "请选择形象" }]}
          >
            <Select
              placeholder="选择形象（未创建请先到「数字人形象」Tab 新建）"
              options={avatars.map((a) => ({
                value: a.id,
                label: `${a.name}${a.status === "disabled" ? "（已停用）" : ""}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="tone" label="风格">
            <Select options={TONE_OPTIONS} />
          </Form.Item>
          <Form.Item name="duration_min" label="目标时长（分钟）">
            <InputNumber min={5} max={480} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <ExportBundleModal
        open={!!exportBundle}
        bundle={exportBundle}
        onClose={() => setExportBundle(null)}
      />
    </div>
  );
}

