import { useState } from "react";
import {
  Button,
  Card,
  Input,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type {
  DealCopyUpdate,
  DealPlatform,
  DealScheme,
  DealSchemeCopy,
} from "../../services/deals";
import {
  copyForPlatform,
  marginLines,
  PLATFORMS,
  PLATFORM_LABELS,
  SCHEME_TYPE_LABELS,
  formatPrice,
} from "../../utils/deals";

const { Text } = Typography;
const { TextArea } = Input;

export interface SchemeCardProps {
  scheme: DealScheme;
  readonly?: boolean;
  generatingPlatform: DealPlatform | null;
  exportingPlatform: DealPlatform | null;
  onGenerateCopy: (platform: DealPlatform) => void;
  onPatchCopy: (platform: DealPlatform, copy: DealSchemeCopy, data: DealCopyUpdate) => void;
  onExport: (platform: DealPlatform) => void;
  onCopyText: (platform: DealPlatform) => void;
  onEditScheme: () => void;
  onDeleteScheme: () => void;
}

export default function SchemeCard({
  scheme,
  readonly = false,
  generatingPlatform,
  exportingPlatform,
  onGenerateCopy,
  onPatchCopy,
  onExport,
  onCopyText,
  onEditScheme,
  onDeleteScheme,
}: SchemeCardProps) {
  const [activePlatform, setActivePlatform] = useState<DealPlatform>("douyin");
  const [editingCopy, setEditingCopy] = useState(false);
  const [copyDraft, setCopyDraft] = useState<DealCopyUpdate>({});

  const margin = marginLines(scheme.margin_estimate);
  const negative = (scheme.margin_estimate?.net_margin ?? 0) < 0;

  const startEditCopy = (copy: DealSchemeCopy | undefined) => {
    setCopyDraft({
      title: copy?.title ?? "",
      selling_points: copy?.selling_points ?? [],
      rules: copy?.rules ?? "",
      cover_prompt: copy?.cover_prompt ?? "",
    });
    setEditingCopy(true);
  };

  const saveCopy = async (copy: DealSchemeCopy | undefined) => {
    if (!copy) return;
    onPatchCopy(activePlatform, copy, copyDraft);
    setEditingCopy(false);
  };

  const renderPlatformBody = (platform: DealPlatform) => {
    const copy = copyForPlatform(scheme, platform);
    const generating = generatingPlatform === platform;
    const exporting = exportingPlatform === platform;
    if (readonly) {
      return copy ? (
        <div style={{ padding: "4px 0" }}>
          <Text strong>{copy.title}</Text>
          {copy.selling_points?.map((p, i) => (
            <div key={i} style={{ marginTop: 4 }}>
              · {p}
            </div>
          ))}
          {copy.rules && (
            <Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 12 }}>
              {copy.rules}
            </Text>
          )}
        </div>
      ) : (
        <Text type="secondary">该平台尚未生成文案</Text>
      );
    }

    if (!copy) {
      return (
        <Button
          type="primary"
          ghost
          icon={<ThunderboltOutlined />}
          loading={generating}
          onClick={() => onGenerateCopy(platform)}
        >
          生成该平台文案
        </Button>
      );
    }

    return (
      <div>
        {!editingCopy ? (
          <>
            <Text strong>{copy.title}</Text>
            {copy.selling_points?.map((p, i) => (
              <div key={i} style={{ marginTop: 4 }}>
                · {p}
              </div>
            ))}
            {copy.rules && (
              <Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 12 }}>
                {copy.rules}
              </Text>
            )}
            <div style={{ marginTop: 10 }}>
              <Space wrap>
                <Button size="small" icon={<EditOutlined />} onClick={() => startEditCopy(copy)}>
                  编辑
                </Button>
                <Button size="small" icon={<CopyOutlined />} onClick={() => onCopyText(platform)}>
                  复制上线文案
                </Button>
                <Button
                  size="small"
                  type="primary"
                  icon={<ExportOutlined />}
                  loading={exporting}
                  onClick={() => onExport(platform)}
                >
                  导出该平台视觉设计
                </Button>
              </Space>
            </div>
          </>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <Input
              placeholder="标题"
              value={copyDraft.title}
              onChange={(e) => setCopyDraft({ ...copyDraft, title: e.target.value })}
              maxLength={200}
            />
            <TextArea
              placeholder="卖点（每行一条）"
              autoSize={{ minRows: 2, maxRows: 5 }}
              value={(copyDraft.selling_points ?? []).join("\n")}
              onChange={(e) =>
                setCopyDraft({
                  ...copyDraft,
                  selling_points: e.target.value
                    .split("\n")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
            <TextArea
              placeholder="使用规则"
              autoSize={{ minRows: 1, maxRows: 3 }}
              value={copyDraft.rules ?? ""}
              onChange={(e) => setCopyDraft({ ...copyDraft, rules: e.target.value })}
            />
            <TextArea
              placeholder="封面生图 prompt"
              autoSize={{ minRows: 2, maxRows: 5 }}
              value={copyDraft.cover_prompt ?? ""}
              onChange={(e) => setCopyDraft({ ...copyDraft, cover_prompt: e.target.value })}
            />
            <Space>
              <Button type="primary" size="small" icon={<SaveOutlined />} onClick={() => saveCopy(copy)}>
                保存
              </Button>
              <Button size="small" onClick={() => setEditingCopy(false)}>
                取消
              </Button>
            </Space>
          </div>
        )}
      </div>
    );
  };

  return (
    <Card
      title={
        <Space>
          <Tag
            color={
              scheme.scheme_type === "profit"
                ? "gold"
                : scheme.scheme_type === "hook"
                  ? "green"
                  : "purple"
            }
          >
            {SCHEME_TYPE_LABELS[scheme.scheme_type] || scheme.scheme_type}
          </Tag>
          <Text strong>{scheme.title}</Text>
          {scheme.status === "edited" && <Tag color="orange">已编辑</Tag>}
          {readonly && <Tag>只读</Tag>}
        </Space>
      }
      extra={
        !readonly && (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={onEditScheme}>
              编辑方案
            </Button>
            <Popconfirm title="确定删除该方案？" onConfirm={onDeleteScheme}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        )
      }
      style={{ marginBottom: 16 }}
    >
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          组合：
        </Text>
        <div style={{ marginTop: 4 }}>
          {(scheme.items ?? []).map((it) => (
            <Tag key={it.item_id} style={{ marginBottom: 4 }}>
              {it.name} ×{it.qty}
              <Text type="secondary" style={{ fontSize: 12 }}>
                （售价 {formatPrice(it.sale_price)} / 成本 {formatPrice(it.cost_price)}）
              </Text>
            </Tag>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          <Text>原价 {formatPrice(scheme.original_price)} → 团购价 </Text>
          <Text strong>{formatPrice(scheme.deal_price)}</Text>
          <Text type="secondary" style={{ marginLeft: 12 }}>
            成本估算 {formatPrice(scheme.cost_estimate)}
          </Text>
        </div>
        <div style={{ marginTop: 8 }}>
          <Text type={negative ? "danger" : undefined}>
            毛利（gross）：{margin.gross} · 净毛利（net）：{margin.net}
          </Text>
          <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
            佣金率 {margin.rate}
          </Text>
        </div>
        {margin.note && (
          <div style={{ marginTop: 4 }}>
            <Text type="warning" style={{ fontSize: 12 }}>
              {margin.note}
            </Text>
          </div>
        )}
      </div>

      <Tabs
        size="small"
        activeKey={activePlatform}
        onChange={(k) => setActivePlatform(k as DealPlatform)}
        items={PLATFORMS.map((p) => ({
          key: p,
          label: PLATFORM_LABELS[p],
          children: renderPlatformBody(p),
        }))}
      />
    </Card>
  );
}

