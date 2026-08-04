import { useEffect } from "react";
import { Button, Modal, Popover, Tag } from "antd";
import { CheckCircleOutlined, CloseCircleOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import type { DeckImage, QaReport } from "../../services/studio";

export function QaBadge({ qa, page }: { qa: QaReport | null | undefined; page: number }) {
  const item = qa?.pages?.find((p) => p.page === page);
  if (!item) return <Tag>—</Tag>;
  if (item.pass) {
    return (
      <Tag icon={<CheckCircleOutlined />} color="success">
        通过 · 密度 {item.checks.density.coverage}%
      </Tag>
    );
  }
  return (
    <Popover
      title={`第 ${page} 页 QA 问题`}
      content={
        <ul style={{ margin: 0, paddingLeft: 16, maxWidth: 260 }}>
          {item.issues.map((iss, i) => (
            <li key={i}>{iss}</li>
          ))}
        </ul>
      }
    >
      <Tag icon={<CloseCircleOutlined />} color="error" style={{ cursor: "pointer" }}>
        未通过 · 密度 {item.checks.density.coverage}%
      </Tag>
    </Popover>
  );
}

export default function DeckPreviewModal({
  open,
  images,
  qaReport,
  index,
  onClose,
  onIndexChange,
}: {
  open: boolean;
  images: DeckImage[];
  qaReport: QaReport | null | undefined;
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}) {
  const total = images.length;
  const img = images[index];

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") onIndexChange(Math.max(0, index - 1));
      if (e.key === "ArrowRight") onIndexChange(Math.min(total - 1, index + 1));
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, index, total, onIndexChange, onClose]);

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={760}
      title={`卡组预览 · 第 ${index + 1} / ${total} 页`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Button
          icon={<LeftOutlined />}
          onClick={() => onIndexChange(Math.max(0, index - 1))}
          disabled={index <= 0}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          {img && (
            <img
              src={img.url}
              alt={`第 ${img.page} 页`}
              style={{
                width: "100%",
                maxHeight: "70vh",
                objectFit: "contain",
                borderRadius: 8,
                background: "#fafafa",
                border: "1px solid #eee",
              }}
            />
          )}
          <div style={{ marginTop: 12, textAlign: "center" }}>
            {img && <QaBadge qa={qaReport} page={img.page} />}
          </div>
        </div>
        <Button
          icon={<RightOutlined />}
          onClick={() => onIndexChange(Math.min(total - 1, index + 1))}
          disabled={index >= total - 1}
        />
      </div>
      <div style={{ marginTop: 12, textAlign: "center", color: "#999", fontSize: 12 }}>
        支持 ← → 方向键翻页，Esc 关闭
      </div>
    </Modal>
  );
}
