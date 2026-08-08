import { useEffect, useState } from "react";
import { Button, Drawer, Input, message, Space, Typography } from "antd";
import { SaveOutlined } from "@ant-design/icons";
import { getSettings, updateSettings, type ApiKeyStatus, type SettingsResponse, type SettingsUpdate } from "../services/settings";
import { updateUser } from "../services/auth";
import { useAuthStore } from "../store/auth";

const { Text } = Typography;

function ApiSection(props: {
  title: string;
  status: ApiKeyStatus | undefined;
  apiKey: string;
  setApiKey: (v: string) => void;
  baseUrl: string;
  setBaseUrl: (v: string) => void;
  model: string;
  setModel: (v: string) => void;
  clear: boolean;
  setClear: (v: boolean) => void;
}) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div className="app-micro" style={{ marginBottom: 8 }}>
        [ {props.title} ] {props.status?.configured ? <span style={{ color: "#178A54" }}>已配置 {props.status.preview}</span> : <span style={{ color: "#E61919" }}>未配置</span>}
      </div>
      <Space direction="vertical" style={{ width: "100%" }} size={8}>
        <Input.Password
          placeholder={props.status?.configured ? "已配置，留空保持不变" : "输入 API 密钥"}
          value={props.apiKey}
          onChange={(e) => props.setApiKey(e.target.value)}
          autoComplete="new-password"
        />
        <Input placeholder="Base URL" value={props.baseUrl} onChange={(e) => props.setBaseUrl(e.target.value)} />
        <Input placeholder="模型名" value={props.model} onChange={(e) => props.setModel(e.target.value)} />
        <Button
          type="link"
          size="small"
          style={{ padding: 0, height: "auto", color: props.clear ? "#E61919" : undefined }}
          onClick={() => props.setClear(!props.clear)}
        >
          {props.clear ? "已选择清除，保存后生效" : "清除已配置密钥"}
        </Button>
      </Space>
    </div>
  );
}

export default function SettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [storageDir, setStorageDir] = useState("");
  const [textKey, setTextKey] = useState("");
  const [textBase, setTextBase] = useState("");
  const [textModel, setTextModel] = useState("");
  const [imageKey, setImageKey] = useState("");
  const [imageBase, setImageBase] = useState("");
  const [imageModel, setImageModel] = useState("");
  const [videoKey, setVideoKey] = useState("");
  const [videoBase, setVideoBase] = useState("");
  const [videoModel, setVideoModel] = useState("");
  const [clearText, setClearText] = useState(false);
  const [clearImage, setClearImage] = useState(false);
  const [clearVideo, setClearVideo] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);

  useEffect(() => {
    if (!open) return;
    getSettings()
      .then((s) => {
        setSettings(s);
        setStorageDir(s.storage.current_dir);
        setTextKey("");
        setTextBase(s.text.base_url);
        setTextModel(s.text.model);
        setImageKey("");
        setImageBase(s.image.base_url);
        setImageModel(s.image.model);
        setVideoKey("");
        setVideoBase(s.video.base_url);
        setVideoModel(s.video.model);
        setClearText(false);
        setClearImage(false);
        setClearVideo(false);
        setName(user?.name || "");
        setPassword("");
        setConfirm("");
      })
      .catch(() => message.error("读取设置失败"));
  }, [open, user?.name]);

  const save = async () => {
    if (password && password.length < 8) {
      message.error("新密码至少 8 位");
      return;
    }
    if (password !== confirm) {
      message.error("两次输入的密码不一致");
      return;
    }
    setSaving(true);
    try {
      const body: SettingsUpdate = {};
      if (storageDir && storageDir !== settings?.storage.current_dir) {
        body.storage_dir = storageDir;
      }
      body.text = {
        api_key: clearText ? "" : textKey || undefined,
        base_url: textBase || undefined,
        model: textModel || undefined,
      };
      body.image = {
        api_key: clearImage ? "" : imageKey || undefined,
        base_url: imageBase || undefined,
        model: imageModel || undefined,
      };
      body.video = {
        api_key: clearVideo ? "" : videoKey || undefined,
        base_url: videoBase || undefined,
        model: videoModel || undefined,
      };
      const res = await updateSettings(body);
      setSettings(res);
      if (name && (name !== user?.name || password)) {
        const u = await updateUser(name, password || undefined);
        if (token) setAuth(token, u);
      }
      message.success("设置已保存");
      setPassword("");
      setConfirm("");
      onClose();
    } catch {
      message.error("保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={<span className="app-micro">[ 系统设置 / SETTINGS ]</span>}
      width={460}
      open={open}
      onClose={onClose}
      extra={
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>
          保存
        </Button>
      }
    >
      <div className="app-micro" style={{ marginBottom: 8 }}>
        [ 文件保存位置 ]
      </div>
      <Input
        value={storageDir}
        onChange={(e) => setStorageDir(e.target.value)}
        placeholder="媒体文件保存目录"
      />
      <Text type="secondary" style={{ display: "block", margin: "6px 0 18px", fontSize: 12 }}>
        修改后新文件写入新目录，历史文件仍可访问。
      </Text>

      <ApiSection
        title="文字 API · DeepSeek"
        status={settings?.text}
        apiKey={textKey}
        setApiKey={setTextKey}
        baseUrl={textBase}
        setBaseUrl={setTextBase}
        model={textModel}
        setModel={setTextModel}
        clear={clearText}
        setClear={setClearText}
      />
      <ApiSection
        title="图片 API · 火山引擎豆包"
        status={settings?.image}
        apiKey={imageKey}
        setApiKey={setImageKey}
        baseUrl={imageBase}
        setBaseUrl={setImageBase}
        model={imageModel}
        setModel={setImageModel}
        clear={clearImage}
        setClear={setClearImage}
      />
      <ApiSection
        title="视频 API（预留）"
        status={settings?.video}
        apiKey={videoKey}
        setApiKey={setVideoKey}
        baseUrl={videoBase}
        setBaseUrl={setVideoBase}
        model={videoModel}
        setModel={setVideoModel}
        clear={clearVideo}
        setClear={setClearVideo}
      />

      <div className="app-micro" style={{ margin: "18px 0 8px" }}>
        [ 用户信息 ]
      </div>
      <Space direction="vertical" style={{ width: "100%" }} size={8}>
        <Input placeholder="姓名 / 团队名" value={name} onChange={(e) => setName(e.target.value)} />
        <Input.Password placeholder="新密码（至少 8 位，留空不改）" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        <Input.Password placeholder="确认新密码" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
      </Space>
    </Drawer>
  );
}