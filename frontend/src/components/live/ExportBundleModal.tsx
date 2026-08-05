import { Button, Collapse, Modal, Space, Tag, Typography, message } from "antd";
import {
  CheckCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import type { LiveExportBundle } from "../../services/live";
import { REPLY_MODE_LABELS } from "../../utils/live";

const { Text } = Typography;

function copyText(text: string, label: string) {
  navigator.clipboard
    ?.writeText(text)
    .then(() => message.success(`${label}已复制`))
    .catch(() => message.error("复制失败，请手动选择复制"));
}

function downloadText(filename: string, text: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadBundle(bundle: LiveExportBundle) {
  const date = new Date().toISOString().slice(0, 10);
  downloadText(
    `livestream-bundle-${date}.json`,
    JSON.stringify(bundle, null, 2),
    "application/json;charset=utf-8"
  );
}

function downloadEngineFiles(bundle: LiveExportBundle) {
  // digital-human-livestream 可直接读取的文件：persona.json / wordlist.txt
  downloadText("persona.json", JSON.stringify(bundle.persona_json, null, 2), "application/json;charset=utf-8");
  downloadText("wordlist.txt", bundle.wordlist.join("\n"));
  downloadText("script.md", bundle.script_markdown);
  downloadText("reply_rules.json", JSON.stringify(bundle.reply_rules, null, 2), "application/json;charset=utf-8");
  downloadText("engine_guide.txt", bundle.engine_guide);
}

const CODE_STYLE: React.CSSProperties = {
  whiteSpace: "pre-wrap",
  background: "#fafafa",
  padding: 12,
  borderRadius: 8,
  maxHeight: 320,
  overflow: "auto",
};

interface Props {
  open: boolean;
  bundle: LiveExportBundle | null;
  onClose: () => void;
}

export default function ExportBundleModal({ open, bundle, onClose }: Props) {
  if (!bundle) return null;

  return (
    <Modal
      title="导出开播包"
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <Button icon={<DownloadOutlined />} onClick={() => downloadEngineFiles(bundle)}>
            下载引擎文件
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => downloadBundle(bundle)}>
            下载开播包
          </Button>
          <Button type="primary" onClick={onClose}>
            关闭
          </Button>
        </Space>
      }
      width={820}
    >
      {bundle.compliance.items
        .filter((i) => !i.ok)
        .map((i) => (
          <Tag key={i.key} color="red" icon={<ExclamationCircleOutlined />} style={{ marginBottom: 6 }}>
            {i.detail}
          </Tag>
        ))}

      <Collapse
        defaultActiveKey={["script", "compliance"]}
        items={[
          {
            key: "script",
            label: (
              <Space>
                <Text strong>脚本 Markdown</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => copyText(bundle.script_markdown, "脚本")}
                >
                  复制
                </Button>
              </Space>
            ),
            children: <pre style={CODE_STYLE}>{bundle.script_markdown}</pre>,
          },
          {
            key: "persona",
            label: (
              <Space>
                <Text strong>persona.json</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() =>
                    copyText(JSON.stringify(bundle.persona_json, null, 2), "persona.json")
                  }
                >
                  复制
                </Button>
              </Space>
            ),
            children: (
              <pre style={CODE_STYLE}>
                {JSON.stringify(bundle.persona_json, null, 2)}
              </pre>
            ),
          },
          {
            key: "wordlist",
            label: (
              <Space>
                <Text strong>wordlist（双向敏感词）</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => copyText(bundle.wordlist.join("\n"), "wordlist")}
                >
                  复制
                </Button>
              </Space>
            ),
            children:
              bundle.wordlist.length === 0 ? (
                <Text type="secondary">（空）</Text>
              ) : (
                bundle.wordlist.map((w) => <Tag key={w}>{w}</Tag>)
              ),
          },
          {
            key: "reply",
            label: (
              <Space>
                <Text strong>弹幕回复规则</Text>
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() =>
                    copyText(JSON.stringify(bundle.reply_rules, null, 2), "回复规则")
                  }
                >
                  复制
                </Button>
              </Space>
            ),
            children:
              bundle.reply_rules.length === 0 ? (
                <Text type="secondary">未配置弹幕互动规则（MVP 以人工粘贴候选话术为主）</Text>
              ) : (
                bundle.reply_rules.map((r, idx) => (
                  <div key={idx} style={{ marginBottom: 8 }}>
                    <Tag color="geekblue">{r.trigger}</Tag>
                    <Tag color={r.mode === "auto" ? "green" : "orange"}>
                      {REPLY_MODE_LABELS[r.mode] ?? r.mode}
                    </Tag>
                    <Text>{r.reply}</Text>
                  </div>
                ))
              ),
          },
          {
            key: "compliance",
            label: (
              <Space>
                <Text strong>合规清单</Text>
                {bundle.compliance.pass ? (
                  <Tag color="green" icon={<CheckCircleOutlined />}>
                    通过
                  </Tag>
                ) : (
                  <Tag color="red" icon={<ExclamationCircleOutlined />}>
                    未通过
                  </Tag>
                )}
              </Space>
            ),
            children: (
              <div>
                {bundle.compliance.items.map((i) => (
                  <div key={i.key} style={{ marginBottom: 4 }}>
                    {i.ok ? (
                      <CheckCircleOutlined style={{ color: "#52c41a", marginRight: 6 }} />
                    ) : (
                      <ExclamationCircleOutlined style={{ color: "#ff4d4f", marginRight: 6 }} />
                    )}
                    <Text type={i.ok ? "secondary" : undefined}>{i.detail}</Text>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: "guide",
            label: <Text strong>引擎启动说明</Text>,
            children: (
              <pre style={{ ...CODE_STYLE, background: "#fff7e6" }}>
                {bundle.engine_guide}
              </pre>
            ),
          },
        ]}
      />
    </Modal>
  );
}
