import { Button, Modal, Space, Tag } from "antd";
import type { AssetCandidate } from "../../services/designs";

export default function CandidatesModal({
  open,
  title,
  candidates,
  loading,
  confirmingAid,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  candidates: AssetCandidate[];
  loading: boolean;
  confirmingAid: string | null;
  onCancel: () => void;
  onConfirm: (candidate: AssetCandidate) => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onCancel={onCancel}
      width={760}
      footer={null}
    >
      {loading && <div style={{ textAlign: "center", padding: 32 }}>生成中...</div>}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {candidates.map((candidate, index) => (
          <div
            key={candidate.aid}
            style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", background: "#fff" }}
          >
            <img
              src={candidate.url}
              alt={`候选 ${index + 1}`}
              style={{ width: "100%", aspectRatio: "1/1", objectFit: "cover", display: "block" }}
            />
            <div style={{ padding: 8 }}>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Tag color="orange">候选 {index + 1}</Tag>
                <Button
                  type="primary"
                  size="small"
                  block
                  loading={confirmingAid === candidate.aid}
                  onClick={() => onConfirm(candidate)}
                >
                  应用这张
                </Button>
              </Space>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
