import { useState } from "react";
import { Button, Drawer, Form, Input, message, Radio, Space, Spin, Tag, Upload } from "antd";
import { PictureOutlined, UploadOutlined } from "@ant-design/icons";
import { designService, type AssetCandidate, type DesignAssetType } from "../../services/designs";
import { getApiError } from "../../utils/errors";

const { TextArea } = Input;

export default function AiGenerateDrawer({
  open,
  projectId,
  onClose,
  onConfirm,
}: {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onConfirm: (candidate: AssetCandidate) => Promise<void>;
}) {
  const [prompt, setPrompt] = useState("");
  const [assetType, setAssetType] = useState<DesignAssetType>("photo");
  const [refFile, setRefFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<AssetCandidate[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning("请输入提示词");
      return;
    }
    setGenerating(true);
    try {
      const res = await designService.generateAssets(projectId, prompt.trim(), refFile, assetType);
      setCandidates(res.data.candidates);
      setBatchId(res.data.batch_id);
    } catch (e) {
      message.error(getApiError(e));
    } finally {
      setGenerating(false);
    }
  };

  const handleConfirm = async (candidate: AssetCandidate) => {
    setConfirming(candidate.aid);
    try {
      await onConfirm(candidate);
      setCandidates([]);
      setBatchId(null);
      setPrompt("");
      setRefFile(null);
      onClose();
    } catch (e) {
      message.error(getApiError(e));
    } finally {
      setConfirming(null);
    }
  };

  return (
    <Drawer
      open={open}
      title="AI 生成图片"
      width={560}
      onClose={onClose}
      extra={
        <Tag color={batchId ? "green" : "default"}>
          {candidates.length > 0 ? `已生成 ${candidates.length} 张候选` : "未生成"}
        </Tag>
      }
    >
      <Form layout="vertical">
        <Form.Item label="提示词">
          <TextArea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="描述菜品、氛围、构图，例如：深夜食堂暖光下的红烧肉特写"
            maxLength={1000}
          />
        </Form.Item>
        <Form.Item label="素材类型">
          <Radio.Group
            value={assetType}
            onChange={(e) => setAssetType(e.target.value)}
            options={[
              { label: "菜品", value: "dish" },
              { label: "Logo", value: "logo" },
              { label: "照片", value: "photo" },
            ]}
            optionType="button"
          />
        </Form.Item>
        <Form.Item label="参考图（可选）">
          <Upload
            accept="image/png,image/jpeg,image/webp"
            showUploadList={false}
            beforeUpload={(file) => {
              setRefFile(file);
              message.info(`参考图已选：${file.name}`);
              return false;
            }}
          >
            <Button icon={<UploadOutlined />}>
              {refFile ? refFile.name : "上传参考图"}
            </Button>
          </Upload>
        </Form.Item>
        <Button
          type="primary"
          icon={<PictureOutlined />}
          loading={generating}
          onClick={handleGenerate}
          block
        >
          生成 4 张候选
        </Button>
      </Form>

      {generating && (
        <div style={{ textAlign: "center", padding: 32 }}>
          <Spin tip="豆包生成中，通常需要 20-60 秒" />
        </div>
      )}

      {!generating && candidates.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {candidates.map((candidate, index) => (
              <div
                key={candidate.aid}
                style={{
                  border: "1px solid #eee",
                  borderRadius: 8,
                  overflow: "hidden",
                  background: "#fff",
                }}
              >
                <img
                  src={candidate.url}
                  alt={`候选 ${index + 1}`}
                  style={{ width: "100%", aspectRatio: "1/1", objectFit: "cover", display: "block" }}
                />
                <div style={{ padding: 8 }}>
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Tag color="blue">候选 {index + 1}</Tag>
                    <Button
                      type="primary"
                      size="small"
                      block
                      loading={confirming === candidate.aid}
                      onClick={() => handleConfirm(candidate)}
                    >
                      选择这张
                    </Button>
                  </Space>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Drawer>
  );
}
