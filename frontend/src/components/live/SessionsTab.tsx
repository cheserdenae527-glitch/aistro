import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  SaveOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/auth";
import {
  liveService,
  type LiveAvatar,
  type LiveScript,
  type LiveSession,
  type LiveSessionMetric,
  type SessionMetrics,
} from "../../services/live";
import {
  formatDateTime,
  formatGmv,
  SESSION_STATUS_COLORS,
  SESSION_STATUS_LABELS,
  sessionScriptLabel,
} from "../../utils/live";
import { showApiError } from "../../utils/errors";

const { Text } = Typography;

interface Props {
  projectId: string;
  scripts: LiveScript[];
  avatars: LiveAvatar[];
  aiLabelText: string;
}

interface CreateForm {
  script_id?: string;
  avatar_id?: string;
  scheduled_at: Dayjs;
  duration_min?: number;
  notes?: string;
}

interface LiveForm {
  operator_id: string;
  duty_confirmed: boolean;
  ai_label_confirmed: boolean;
}

interface MetricsForm {
  viewers?: number;
  peak_viewers?: number;
  avg_watch_sec?: number;
  interaction_count?: number;
  danmaku_count?: number;
  order_count?: number;
  gmv?: number;
  redemption_count?: number;
  note?: string;
}

const _NUMERIC_METRIC_KEYS = [
  "viewers",
  "peak_viewers",
  "avg_watch_sec",
  "interaction_count",
  "danmaku_count",
  "order_count",
  "gmv",
  "redemption_count",
] as const;
type NumericMetricKey = (typeof _NUMERIC_METRIC_KEYS)[number];

const METRICS_FIELDS: { key: NumericMetricKey; label: string }[] = [
  { key: "viewers", label: "观看人数" },
  { key: "peak_viewers", label: "峰值在线" },
  { key: "avg_watch_sec", label: "平均停留(s)" },
  { key: "interaction_count", label: "互动数" },
  { key: "danmaku_count", label: "弹幕数" },
  { key: "order_count", label: "订单数" },
  { key: "gmv", label: "GMV(元)" },
  { key: "redemption_count", label: "核销数" },
];

function toMetricsForm(m: SessionMetrics | null | undefined): MetricsForm {
  const out: MetricsForm = {};
  for (const f of METRICS_FIELDS) {
    const v = m?.[f.key];
    if (v !== null && v !== undefined) out[f.key] = Number(v);
  }
  out.note = m?.note ?? undefined;
  return out;
}

export default function SessionsTab({ projectId, scripts, avatars, aiLabelText }: Props) {
  const started = useRef(false);
  const currentUser = useAuthStore((s) => s.user);
  const [loading, setLoading] = useState(true);
  const [sessions, setSessions] = useState<LiveSession[]>([]);

  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm] = Form.useForm<CreateForm>();

  const [starting, setStarting] = useState<LiveSession | null>(null);
  const [liveForm] = Form.useForm<LiveForm>();
  const [startingSubmitting, setStartingSubmitting] = useState(false);

  const [backfill, setBackfill] = useState<LiveSession | null>(null);
  const [backfillForm] = Form.useForm<{ started_at: Dayjs; ended_at: Dayjs }>();
  const [backfillSubmitting, setBackfillSubmitting] = useState(false);

  const [editSession, setEditSession] = useState<LiveSession | null>(null);
  const [editForm] = Form.useForm<CreateForm>();
  const [editSubmitting, setEditSubmitting] = useState(false);

  const [noteSession, setNoteSession] = useState<LiveSession | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteSubmitting, setNoteSubmitting] = useState(false);

  const [metricsMap, setMetricsMap] = useState<Record<string, LiveSessionMetric>>({});
  const [metricsForms, setMetricsForms] = useState<Record<string, MetricsForm>>({});
  const [savingMetrics, setSavingMetrics] = useState<Record<string, boolean>>({});
  const [reviewing, setReviewing] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<readonly React.Key[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await liveService.listSessions(projectId, { page: 1, page_size: 100 });
      setSessions(res.data.items);
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

  const confirmedScripts = scripts.filter((s) => !s.is_archived && s.status === "confirmed");

  const openCreate = () => {
    createForm.resetFields();
    createForm.setFieldsValue({ scheduled_at: dayjs().add(1, "day").hour(20).minute(0).second(0) });
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    let values;
    try {
      values = await createForm.validateFields();
    } catch {
      return; // 校验未通过
    }
    setCreating(true);
    try {
      const res = await liveService.createSession(projectId, {
        script_id: values.script_id ?? null,
        avatar_id: values.avatar_id ?? null,
        scheduled_at: values.scheduled_at.toISOString(),
        duration_min: values.duration_min ?? null,
        notes: values.notes ?? null,
      });
      setSessions((prev) => [...prev, res.data]);
      setCreateOpen(false);
      message.success("场次已排期");
    } catch (e) {
      showApiError(e);
    } finally {
      setCreating(false);
    }
  };

  const openStart = (session: LiveSession) => {
    liveForm.setFieldsValue({
      operator_id: currentUser?.id ?? "",
      duty_confirmed: false,
      ai_label_confirmed: false,
    });
    setStarting(session);
  };

  const handleStart = async () => {
    if (!starting) return;
    let values;
    try {
      values = await liveForm.validateFields();
    } catch {
      return;
    }
    if (!values.duty_confirmed || !values.ai_label_confirmed || !values.operator_id) {
      message.warning("请确认值守人、值守确认与 AI 标识确认");
      return;
    }
    setStartingSubmitting(true);
    try {
      const res = await liveService.updateSession(projectId, starting.id, {
        operator_id: values.operator_id,
        duty_confirmed: true,
        ai_label_confirmed: true,
        status: "live",
      });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setStarting(null);
      message.success("场次已开播");
    } catch (e) {
      showApiError(e);
    } finally {
      setStartingSubmitting(false);
    }
  };

  const handleEnd = async (session: LiveSession) => {
    try {
      const res = await liveService.updateSession(projectId, session.id, { status: "ended" });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      message.success("场次已结束");
    } catch (e) {
      showApiError(e);
    }
  };

  const handleCancel = async (session: LiveSession) => {
    try {
      const res = await liveService.updateSession(projectId, session.id, { status: "cancelled" });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      message.success("场次已取消");
    } catch (e) {
      showApiError(e);
    }
  };

  const openBackfill = (session: LiveSession) => {
    backfillForm.resetFields();
    setBackfill(session);
  };

  const handleBackfill = async () => {
    if (!backfill) return;
    let values;
    try {
      values = await backfillForm.validateFields();
    } catch {
      return;
    }
    setBackfillSubmitting(true);
    try {
      const res = await liveService.updateSession(projectId, backfill.id, {
        status: "ended",
        started_at: values.started_at.toISOString(),
        ended_at: values.ended_at.toISOString(),
      });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setBackfill(null);
      message.success("已补录场次（is_backfilled=true）");
    } catch (e) {
      showApiError(e);
    } finally {
      setBackfillSubmitting(false);
    }
  };

  const openEdit = (session: LiveSession) => {
    editForm.setFieldsValue({
      script_id: session.script_id ?? undefined,
      avatar_id: session.avatar_id ?? undefined,
      scheduled_at: dayjs(session.scheduled_at),
      duration_min: session.duration_min ?? undefined,
      notes: session.notes ?? undefined,
    });
    setEditSession(session);
  };

  const handleEdit = async () => {
    if (!editSession) return;
    let values;
    try {
      values = await editForm.validateFields();
    } catch {
      return;
    }
    setEditSubmitting(true);
    try {
      const res = await liveService.updateSession(projectId, editSession.id, {
        script_id: values.script_id ?? null,
        avatar_id: values.avatar_id ?? null,
        scheduled_at: values.scheduled_at.toISOString(),
        duration_min: values.duration_min ?? null,
        notes: values.notes ?? null,
      });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setEditSession(null);
      message.success("场次已更新");
    } catch (e) {
      showApiError(e);
    } finally {
      setEditSubmitting(false);
    }
  };

  const openNote = (session: LiveSession) => {
    setNoteDraft(session.notes ?? "");
    setNoteSession(session);
  };

  const handleNoteSave = async () => {
    if (!noteSession) return;
    setNoteSubmitting(true);
    try {
      const res = await liveService.updateSession(projectId, noteSession.id, {
        notes: noteDraft,
      });
      setSessions((prev) => prev.map((s) => (s.id === res.data.id ? res.data : s)));
      setNoteSession(null);
      message.success("备注已保存");
    } catch (e) {
      showApiError(e);
    } finally {
      setNoteSubmitting(false);
    }
  };

  const handleDelete = async (session: LiveSession) => {
    try {
      await liveService.deleteSession(projectId, session.id);
      setSessions((prev) => prev.filter((s) => s.id !== session.id));
      message.success("场次已删除");
    } catch (e) {
      showApiError(e);
    }
  };

  const loadMetrics = async (sessionId: string) => {
    try {
      const res = await liveService.getMetrics(projectId, sessionId);
      setMetricsMap((prev) => ({ ...prev, [sessionId]: res.data }));
      setMetricsForms((prev) => ({
        ...prev,
        [sessionId]: toMetricsForm(res.data.metrics ?? null),
      }));
    } catch {
      setMetricsMap((prev) => ({ ...prev, [sessionId]: null as unknown as LiveSessionMetric }));
      setMetricsForms((prev) => ({ ...prev, [sessionId]: {} }));
    }
  };

  const handleMetricsExpand = (expandedRows: readonly React.Key[]) => {
    setExpanded(expandedRows);
    expandedRows.forEach((k) => loadMetrics(String(k)));
  };

  const saveMetrics = async (session: LiveSession) => {
    const form = metricsForms[session.id] ?? {};
    const payload: SessionMetrics = {};
    for (const f of METRICS_FIELDS) {
      const v = form[f.key];
      if (v !== undefined && v !== null) payload[f.key] = Number(v);
    }
    payload.note = form.note?.trim() || null;
    setSavingMetrics((prev) => ({ ...prev, [session.id]: true }));
    try {
      const res = await liveService.upsertMetrics(projectId, session.id, {
        metrics: payload,
        source: "manual",
      });
      setMetricsMap((prev) => ({ ...prev, [session.id]: res.data }));
      message.success("复盘数据已保存");
    } catch (e) {
      showApiError(e);
    } finally {
      setSavingMetrics((prev) => ({ ...prev, [session.id]: false }));
    }
  };

  const reviewSession = async (session: LiveSession) => {
    setReviewing((prev) => ({ ...prev, [session.id]: true }));
    try {
      const res = await liveService.reviewSession(projectId, session.id);
      setMetricsMap((prev) => ({
        ...prev,
        [session.id]: { ...(prev[session.id] as LiveSessionMetric), ai_review: res.data.ai_review },
      }));
      message.success("AI 复盘完成");
    } catch (e) {
      showApiError(e);
    } finally {
      setReviewing((prev) => ({ ...prev, [session.id]: false }));
    }
  };

  const columns: ColumnsType<LiveSession> = [
    {
      title: "排期",
      dataIndex: "scheduled_at",
      render: (v: string) => <Text>{formatDateTime(v)}</Text>,
    },
    {
      title: "时长",
      dataIndex: "duration_min",
      render: (v: number | null) => (v ? `${v} 分钟` : "-"),
    },
    {
      title: "状态",
      dataIndex: "status",
      render: (v: string, s) => (
        <Space size={4}>
          <Tag color={SESSION_STATUS_COLORS[v]}>{SESSION_STATUS_LABELS[v] ?? v}</Tag>
          {s.is_backfilled && <Tag color="purple">补录</Tag>}
          {s.duty_confirmed && <Tag color="green">值守</Tag>}
        </Space>
      ),
    },
    {
      title: "脚本",
      dataIndex: "script_id",
      render: (_v, s) => <Text>{sessionScriptLabel(s, scripts)}</Text>,
    },
    {
      title: "备注",
      dataIndex: "notes",
      render: (v: string | null) => (
        <Text type="secondary" ellipsis style={{ maxWidth: 200 }}>
          {v || "-"}
        </Text>
      ),
    },
    {
      title: "操作",
      key: "actions",
      render: (_v, s) => {
        const actions: React.ReactNode[] = [];
        if (s.status === "planned") {
          actions.push(
            <Button key="start" size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => openStart(s)}>
              开播
            </Button>,
            <Button key="edit" size="small" icon={<EditOutlined />} onClick={() => openEdit(s)}>
              编辑
            </Button>,
            <Button key="backfill" size="small" onClick={() => openBackfill(s)}>
              补录
            </Button>,
            <Popconfirm key="cancel" title="确定取消该场次？" onConfirm={() => handleCancel(s)}>
              <Button size="small">取消</Button>
            </Popconfirm>,
            <Popconfirm key="del" title="确定删除该场次？" onConfirm={() => handleDelete(s)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          );
        } else if (s.status === "live") {
          actions.push(
            <Popconfirm key="end" title="确定结束该场次？" onConfirm={() => handleEnd(s)}>
              <Button size="small" icon={<StopOutlined />}>
                结束
              </Button>
            </Popconfirm>,
            <Button key="note" size="small" onClick={() => openNote(s)}>
              备注
            </Button>
          );
        } else {
          actions.push(
            <Button key="note" size="small" onClick={() => openNote(s)}>
              备注
            </Button>
          );
        }
        return <Space>{actions}</Space>;
      },
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
        <Text type="secondary">
          场次排期 + 状态流转：开播须值守人确认 + AI 标识确认；未挂脚本的场次为「纯人工直播」。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建场次
        </Button>
      </div>

      {sessions.length === 0 ? (
        <Card>
          <Empty description="暂无场次">
            <Button type="primary" onClick={openCreate}>
              新建场次
            </Button>
          </Empty>
        </Card>
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={sessions}
          pagination={false}
          expandable={{
            expandedRowKeys: expanded,
            onExpandedRowsChange: handleMetricsExpand,
            expandedRowRender: (s) => {
              const form = metricsForms[s.id] ?? {};
              const metric = metricsMap[s.id];
              return (
                <div style={{ padding: 8 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                    {METRICS_FIELDS.map((f) => (
                      <div key={f.key}>
                        <Text type="secondary">{f.label}</Text>
                        <InputNumber
                          style={{ width: "100%" }}
                          value={(form as Record<string, unknown>)[f.key] as number | undefined}
                          onChange={(v) =>
                            setMetricsForms((prev) => ({
                              ...prev,
                              [s.id]: {
                                ...(prev[s.id] ?? {}),
                                [f.key]: v ?? undefined,
                              },
                            }))
                          }
                        />
                      </div>
                    ))}
                  </div>
                  <Input.TextArea
                    style={{ marginTop: 12 }}
                    rows={2}
                    placeholder="备注"
                    value={form.note ?? ""}
                    onChange={(e) =>
                      setMetricsForms((prev) => ({
                        ...prev,
                        [s.id]: { ...(prev[s.id] ?? {}), note: e.target.value },
                      }))
                    }
                  />
                  <Space style={{ marginTop: 12 }}>
                    <Button
                      type="primary"
                      size="small"
                      icon={<SaveOutlined />}
                      loading={savingMetrics[s.id]}
                      onClick={() => saveMetrics(s)}
                    >
                      保存复盘数据
                    </Button>
                    <Button
                      size="small"
                      icon={<RobotOutlined />}
                      loading={reviewing[s.id]}
                      disabled={!metric?.metrics}
                      onClick={() => reviewSession(s)}
                    >
                      AI 复盘
                    </Button>
                  </Space>
                  {metric?.metrics && (
                    <div style={{ marginTop: 12, display: "flex", gap: 16, flexWrap: "wrap" }}>
                      <Tag>观看 {metric.metrics.viewers ?? "-"}</Tag>
                      <Tag>峰值 {metric.metrics.peak_viewers ?? "-"}</Tag>
                      <Tag>订单 {metric.metrics.order_count ?? "-"}</Tag>
                      <Tag>GMV {formatGmv(metric.metrics.gmv)}</Tag>
                      <Tag>核销 {metric.metrics.redemption_count ?? "-"}</Tag>
                    </div>
                  )}
                  {metric?.ai_review && (
                    <Alert
                      type="success"
                      showIcon
                      style={{ marginTop: 12 }}
                      message="AI 复盘"
                      description={<div style={{ whiteSpace: "pre-wrap" }}>{metric.ai_review}</div>}
                    />
                  )}
                </div>
              );
            },
          }}
        />
      )}

      {/* 新建场次 */}
      <Modal
        title="新建场次"
        open={createOpen}
        onOk={handleCreate}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="script_id" label="关联脚本">
            <Select
              allowClear
              placeholder="不选 = 纯人工直播（MVP 弹性）"
              options={confirmedScripts.map((s) => ({
                value: s.id,
                label: `批次 ${s.generation_batch} · ${s.title}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="avatar_id" label="数字人形象（可选）">
            <Select
              allowClear
              options={avatars.map((a) => ({ value: a.id, label: a.name }))}
            />
          </Form.Item>
          <Form.Item
            name="scheduled_at"
            label="开播时间"
            rules={[{ required: true, message: "请选择开播时间" }]}
          >
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="duration_min" label="时长（分钟，可选）">
            <InputNumber min={1} max={1440} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 开播前置确认 */}
      <Modal
        title="开播前置确认"
        open={!!starting}
        onOk={handleStart}
        confirmLoading={startingSubmitting}
        onCancel={() => setStarting(null)}
        okText="确认开播"
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="AI 标识文案（需确认已核对无误）"
          description={aiLabelText || "（项目尚未配置 AI 标识文案，请先在基本信息 Tab 填写）"}
        />
        <Form form={liveForm} layout="vertical">
          <Form.Item name="operator_id" label="值守人" rules={[{ required: true, message: "请选择值守人" }]}>
            <Select
              options={[{ value: currentUser?.id ?? "", label: `当前账号（${currentUser?.name ?? "我"}）` }]}
            />
          </Form.Item>
          <Form.Item name="duty_confirmed" label="真人值守确认" valuePropName="checked">
            <Switch checkedChildren="已确认" unCheckedChildren="未确认" />
          </Form.Item>
          <Form.Item name="ai_label_confirmed" label="AI 标识确认" valuePropName="checked">
            <Switch checkedChildren="已确认" unCheckedChildren="未确认" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 补录 */}
      <Modal
        title="补录已完成场次"
        open={!!backfill}
        onOk={handleBackfill}
        confirmLoading={backfillSubmitting}
        onCancel={() => setBackfill(null)}
        okText="保存补录"
      >
        <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
          用于漏排期后补记录已线下完成的场次；保存后标记 is_backfilled=true。
        </Text>
        <Form form={backfillForm} layout="vertical">
          <Form.Item name="started_at" label="开始时间" rules={[{ required: true, message: "必填" }]}>
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="ended_at" label="结束时间" rules={[{ required: true, message: "必填" }]}>
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑排期（planned） */}
      <Modal
        title="编辑场次"
        open={!!editSession}
        onOk={handleEdit}
        confirmLoading={editSubmitting}
        onCancel={() => setEditSession(null)}
        okText="保存"
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="script_id" label="关联脚本">
            <Select
              allowClear
              options={confirmedScripts.map((s) => ({
                value: s.id,
                label: `批次 ${s.generation_batch} · ${s.title}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="avatar_id" label="数字人形象（可选）">
            <Select allowClear options={avatars.map((a) => ({ value: a.id, label: a.name }))} />
          </Form.Item>
          <Form.Item name="scheduled_at" label="开播时间" rules={[{ required: true, message: "请选择开播时间" }]}>
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="duration_min" label="时长（分钟）">
            <InputNumber min={1} max={1440} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 备注（live / 终态） */}
      <Modal
        title="编辑备注"
        open={!!noteSession}
        onOk={handleNoteSave}
        confirmLoading={noteSubmitting}
        onCancel={() => setNoteSession(null)}
        okText="保存"
      >
        <Input.TextArea rows={4} value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} />
      </Modal>
    </div>
  );
}


