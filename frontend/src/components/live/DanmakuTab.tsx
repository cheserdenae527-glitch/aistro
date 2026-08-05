import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, PlusOutlined, SaveOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  liveService,
  type LiveDanmakuConfig,
  type LiveScript,
  type ReplyMode,
} from "../../services/live";
import { REPLY_MODE_LABELS } from "../../utils/live";
import { showApiError } from "../../utils/errors";

const { Text, Title } = Typography;

interface Props {
  projectId: string;
  /** 活跃已定稿脚本（生成弹幕的前置） */
  activeScript: LiveScript | null;
}

interface RuleDraft {
  trigger: string;
  reply: string;
  mode: ReplyMode;
}

export default function DanmakuTab({ projectId, activeScript }: Props) {
  const started = useRef(false);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<LiveDanmakuConfig | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const [personaText, setPersonaText] = useState("");
  const [rules, setRules] = useState<RuleDraft[]>([]);
  const [sensitiveText, setSensitiveText] = useState("");
  const [escalateText, setEscalateText] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await liveService.getDanmaku(projectId);
      setConfig(res.data);
    } catch {
      setConfig(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load();
  }, [load]);

  const openEdit = () => {
    const c = config;
    setPersonaText(JSON.stringify(c?.persona ?? {}, null, 2));
    setRules((c?.reply_rules ?? []).map((r) => ({ ...r })));
    setSensitiveText((c?.sensitive_words ?? []).join("\n"));
    setEscalateText((c?.escalate_topics ?? []).join("\n"));
    setEditOpen(true);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await liveService.generateDanmaku(projectId);
      setConfig(res.data);
      message.success("弹幕规则已生成");
    } catch (e) {
      showApiError(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    const replyRules = rules
      .filter((r) => r.trigger.trim() && r.reply.trim())
      .map((r) => ({ trigger: r.trigger.trim(), reply: r.reply.trim(), mode: r.mode }));
    const sensitive_words = sensitiveText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const escalate_topics = escalateText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    let persona: Record<string, unknown> | null = null;
    try {
      const parsed = JSON.parse(personaText || "{}");
      if (parsed && typeof parsed === "object") persona = parsed;
    } catch {
      message.error("人设必须是合法 JSON");
      setSaving(false);
      return;
    }
    try {
      const res = await liveService.updateDanmaku(projectId, {
        persona,
        reply_rules: replyRules,
        sensitive_words,
        escalate_topics,
      });
      setConfig(res.data);
      setEditOpen(false);
      message.success("弹幕规则已保存");
    } catch (e) {
      showApiError(e);
    } finally {
      setSaving(false);
    }
  };

  const updateRule = (idx: number, patch: Partial<RuleDraft>) => {
    setRules((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <Spin size="large" />
      </div>
    );
  }

  const canGenerate = !!activeScript;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
        <Text type="secondary">
          弹幕互动规则：AI 生成 → 人工微调确认（MVP 以候选话术 + 人工粘贴为主）
          {activeScript ? (
            <Tag color="green" style={{ marginLeft: 8 }}>
              前置已满足：{activeScript.title}
            </Tag>
          ) : (
            <Tag color="orange" style={{ marginLeft: 8 }}>
              需要当前活跃批次已定稿脚本
            </Tag>
          )}
        </Text>
        <Space>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={handleGenerate}
            loading={generating}
            disabled={!canGenerate}
          >
            AI 生成规则
          </Button>
          <Button icon={<SaveOutlined />} onClick={openEdit} disabled={!config}>
            编辑规则
          </Button>
        </Space>
      </div>

      {!config ? (
        <Card>
          <Empty description="尚未生成弹幕互动规则">
            {!canGenerate && (
              <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
                请先在「直播脚本」Tab 生成并定稿当前活跃批次的脚本
              </Text>
            )}
          </Empty>
        </Card>
      ) : (
        <Card
          size="small"
          title="弹幕互动配置"
          extra={
            config.source_script_id ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                基于脚本：{activeScript?.title ?? "历史批次"}
              </Text>
            ) : undefined
          }
        >
          <Title level={5}>回复规则（{rules.length || (config.reply_rules ?? []).length} 条）</Title>
          {(config.reply_rules ?? []).map((r, idx) => (
            <div key={idx} style={{ marginBottom: 8 }}>
              <Tag color="geekblue">{r.trigger}</Tag>
              <Tag color={r.mode === "auto" ? "green" : "orange"}>
                {REPLY_MODE_LABELS[r.mode] ?? r.mode}
              </Tag>
              <Text>{r.reply}</Text>
            </div>
          ))}

          <div style={{ marginTop: 16 }}>
            <Title level={5}>双向敏感词（导出为 wordlist）</Title>
            <div>
              {(config.sensitive_words ?? []).map((w) => (
                <Tag key={w}>{w}</Tag>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <Title level={5}>转人工话题（命中必须转真人）</Title>
            <div>
              {(config.escalate_topics ?? []).map((t) => (
                <Tag key={t} color="red">
                  {t}
                </Tag>
              ))}
            </div>
          </div>

          {config.source_script_id && activeScript && config.source_script_id !== activeScript.id && (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 16 }}
              message="弹幕规则基于其他脚本版本生成"
              description="脚本已重新生成，建议点击「AI 生成规则」重新生成以对齐当前脚本。"
            />
          )}
        </Card>
      )}

      <Modal
        title="编辑弹幕互动规则"
        open={editOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setEditOpen(false)}
        okText="保存"
        width={760}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
          <Card size="small" title="人设（JSON，导出为 persona.json）">
            <Input.TextArea
              rows={8}
              value={personaText}
              onChange={(e) => setPersonaText(e.target.value)}
            />
          </Card>

          <Card
            size="small"
            title="回复规则"
            extra={
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setRules((prev) => [...prev, { trigger: "", reply: "", mode: "manual" }])}
              >
                添加
              </Button>
            }
          >
            {rules.length === 0 && <Text type="secondary">暂无规则，点击「添加」</Text>}
            {rules.map((r, idx) => (
              <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                <Input
                  style={{ width: 160 }}
                  placeholder="触发词"
                  value={r.trigger}
                  onChange={(e) => updateRule(idx, { trigger: e.target.value })}
                />
                <Input
                  style={{ flex: 1 }}
                  placeholder="回复话术"
                  value={r.reply}
                  onChange={(e) => updateRule(idx, { reply: e.target.value })}
                />
                <Select
                  style={{ width: 90 }}
                  value={r.mode}
                  onChange={(v) => updateRule(idx, { mode: v })}
                  options={[
                    { value: "manual", label: "人工" },
                    { value: "auto", label: "自动" },
                  ]}
                />
                <Button
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={() => setRules((prev) => prev.filter((_, i) => i !== idx))}
                />
              </div>
            ))}
          </Card>

          <Card size="small" title="双向敏感词（每行一个，导出为 wordlist）">
            <Input.TextArea rows={4} value={sensitiveText} onChange={(e) => setSensitiveText(e.target.value)} />
          </Card>

          <Card size="small" title="转人工话题（每行一个）">
            <Input.TextArea rows={3} value={escalateText} onChange={(e) => setEscalateText(e.target.value)} />
          </Card>
        </div>
      </Modal>
    </div>
  );
}
