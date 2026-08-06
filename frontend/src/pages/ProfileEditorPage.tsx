import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  Row, Col, Card, Input, Button, Tag, Modal, message, Spin,
  Typography, Divider, Space, Tooltip, Upload, ColorPicker,
} from "antd";
import {
  EyeOutlined, ThunderboltOutlined, UploadOutlined, CopyOutlined,
  SaveOutlined, ScissorOutlined, PictureOutlined, EditOutlined,
  CheckOutlined, CloseOutlined, ZoomInOutlined, DeleteOutlined,
  AuditOutlined, PlusOutlined, HistoryOutlined,
} from "@ant-design/icons";
import type { Color } from "antd/es/color-picker";
import CropModal from "../components/CropModal";
import {
  profileService, type AiVariant,
  type ColorSchemePreset, type HealthCheckResult, type ImageOption, type PinnedNote, type ProfileHistoryItem, type StyleAnalysis,
} from "../services/profiles";

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

// ============================================================
// Types
// ============================================================

interface EditorState {
  nickname: string;
  bio: string;
  colorPrimary: string;
  colorSecondary: string;
  colorAccent: string;
  colorText: string;
  colorMode: "preset" | "custom";
  colorPresetName: string | null;
  avatarUrl: string | null;
  avatarOriginalUrl: string | null;
  avatarPrompt: string;
  bgImageUrl: string | null;
  bgOriginalUrl: string | null;
  bgPrompt: string;
  bioFlagged: boolean;
  pinnedNotes: PinnedNote[];
}

function sameObject(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  try {
    return new URL(a).pathname === new URL(b).pathname;
  } catch {
    return a === b;
  }
}

function HealthCheckBlock({
  title,
  color,
  items,
}: {
  title: string;
  color: string;
  items: string[];
}) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ marginBottom: 6 }}>
      <Text strong style={{ fontSize: 12, color }}>{title}</Text>
      <ul style={{ margin: "2px 0 0", paddingLeft: 18 }}>
        {items.map((item, i) => (
          <li key={i} style={{ marginBottom: 2 }}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ImageOptionsGrid({
  options,
  selectedUrl,
  width,
  height,
  loading,
  onSelect,
  onPreview,
  onRemove,
}: {
  options: ImageOption[];
  selectedUrl: string | null;
  width: number;
  height: number;
  loading: boolean;
  onSelect: (option: ImageOption) => void;
  onPreview: (option: ImageOption) => void;
  onRemove: (option: ImageOption) => void;
}) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  if (options.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>本次生成结果：</Text>
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        {options.map((opt, i) => {
          const selected = opt.url === selectedUrl;
          return (
            <div
              key={opt.object_name}
              onClick={() => onSelect(opt)}
              onDoubleClick={() => onPreview(opt)}
              onMouseEnter={() => setHoveredKey(opt.object_name)}
              onMouseLeave={() => setHoveredKey(null)}
              style={{
                position: "relative",
                width,
                height,
                flex: `0 0 ${width}px`,
                cursor: "pointer",
                borderRadius: 6,
                overflow: "hidden",
                border: selected ? "2px solid #1677ff" : "2px solid rgba(0,0,0,0.12)",
                opacity: selected ? 1 : 0.72,
                boxSizing: "border-box",
              }}
            >
              <img
                src={opt.url}
                alt={`候选图 ${i + 1}`}
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
              />
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 6,
                  background: "rgba(0,0,0,0.35)",
                  opacity: hoveredKey === opt.object_name ? 1 : 0,
                  transition: "opacity 0.15s",
                  pointerEvents: hoveredKey === opt.object_name ? "auto" : "none",
                }}
              >
                <Tooltip title="放大预览" key="zoom">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<ZoomInOutlined />}
                    style={{ background: "rgba(255,255,255,0.9)" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onPreview(opt);
                    }}
                  />
                </Tooltip>
                <Tooltip title="移除" key="remove">
                  <Button
                    size="small"
                    shape="circle"
                    danger
                    icon={<CloseOutlined />}
                    style={{ background: "rgba(255,255,255,0.9)" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemove(opt);
                    }}
                  />
                </Tooltip>
              </div>
              {selected && (
                <div
                  style={{
                    position: "absolute",
                    top: 3,
                    left: 3,
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    background: "#1677ff",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 10,
                  }}
                >
                  <CheckOutlined />
                </div>
              )}
              {loading && (
                <div style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,0.6)" }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ImagePreviewModal({
  open,
  src,
  title,
  onClose,
  onSetCurrent,
  onCrop,
  onRemove,
}: {
  open: boolean;
  src: string | null;
  title: string;
  onClose: () => void;
  onSetCurrent: () => void;
  onCrop: () => void;
  onRemove: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onCancel={onClose}
      width={780}
      footer={[
        <Button key="remove" danger icon={<DeleteOutlined />} onClick={onRemove}>
          移除这张
        </Button>,
        <Button key="crop" icon={<ScissorOutlined />} onClick={onCrop}>
          裁剪
        </Button>,
        <Button key="set" type="primary" icon={<CheckOutlined />} onClick={onSetCurrent}>
          设为当前
        </Button>,
      ]}
    >
      <div style={{ textAlign: "center" }}>
        {src && (
          <img
            src={src}
            alt={title}
            style={{ maxWidth: "100%", maxHeight: 520, borderRadius: 8, display: "inline-block" }}
          />
        )}
      </div>
    </Modal>
  );
}

// ============================================================
// Sub-components
// ============================================================

function PlatformPreview({ state }: { state: EditorState }) {
  const avatarSrc = state.avatarUrl || state.avatarOriginalUrl;
  const bgSrc = state.bgImageUrl || state.bgOriginalUrl;
  return (
    <div style={{
      width: 375, margin: "0 auto", borderRadius: 12, overflow: "hidden",
      background: "#fff", boxShadow: "0 2px 12px rgba(0,0,0,0.1)",
      fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      {/* 背景图 */}
      <div style={{
        width: "100%", height: 140, background: bgSrc
          ? `url(${bgSrc}) center/cover`
          : `linear-gradient(135deg, ${state.colorPrimary}22, ${state.colorSecondary})`,
        position: "relative",
      }}>
        {/* 头像 */}
        <div style={{
          position: "absolute", bottom: -32, left: 16,
          width: 64, height: 64, borderRadius: "50%",
          border: "3px solid #fff",
          background: avatarSrc
            ? `url(${avatarSrc}) center/cover`
            : state.colorPrimary,
          overflow: "hidden",
        }} />
      </div>

      {/* 信息区 */}
      <div style={{ padding: "40px 16px 16px" }}>
        <div style={{ fontWeight: 600, fontSize: 16, color: state.colorText }}>
          {state.nickname || "昵称"}
        </div>
        <div style={{ color: "#999", fontSize: 12, marginTop: 2 }}>小红书号</div>
        <div style={{
          marginTop: 8, fontSize: 13, color: state.colorText,
          whiteSpace: "pre-wrap", lineHeight: 1.6,
        }}>
          {state.bio || "简介文案..."}
        </div>
        <div style={{
          display: "flex", gap: 20, marginTop: 12,
          color: "#999", fontSize: 12,
        }}>
          <span>0 获赞与收藏</span>
          <span>0 关注</span>
          <span>0 粉丝</span>
        </div>
        {state.pinnedNotes.filter((n) => n.title || n.content).slice(0, 3).map((n, i) => (
          <div key={i} style={{ margin: "0 16px 12px", padding: 8, borderRadius: 8, border: "1px solid #f0f0f0", display: "flex", gap: 8 }}>
            <div style={{ width: 44, height: 44, borderRadius: 6, flex: "0 0 44px", background: `linear-gradient(135deg, ${state.colorPrimary}, ${state.colorSecondary})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 600, fontSize: 12 }}>
              {state.nickname ? state.nickname.slice(0, 1) : "笔"}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: state.colorText, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.title || "置顶笔记"}</div>
              <div style={{ fontSize: 11, color: "#999", marginTop: 2, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{n.content || "..."}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProfileEditorPage() {
  const { shop_id, platform } = useParams<{ shop_id: string; platform: string }>();
  const shopId = shop_id!;
  const plat = platform || "xiaohongshu";

  // ---- state ----
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState(0);

  const [state, setState] = useState<EditorState>({
    nickname: "", bio: "",
    colorPrimary: "#C93828", colorSecondary: "#FFF0EE",
    colorAccent: "#A82015", colorText: "#2A0A08",
    colorMode: "preset", colorPresetName: "江湖红",
    avatarUrl: null, avatarOriginalUrl: null, avatarPrompt: "",
    bgImageUrl: null, bgOriginalUrl: null, bgPrompt: "",
    bioFlagged: false,
    pinnedNotes: [],
  });

  // ---- AI generation ----
  const [generating, setGenerating] = useState(false);
  const [variants, setVariants] = useState<AiVariant[]>([]);
  const [genCategory, setGenCategory] = useState("火锅");
  const [genStyle, setGenStyle] = useState("市井烟火");
  const [genPrice, setGenPrice] = useState("人均80");
  const [rateLimitCD, setRateLimitCD] = useState(0);

  // ---- image ----
  const [genAvatarLoading, setGenAvatarLoading] = useState(false);
  const [genBgLoading, setGenBgLoading] = useState(false);
  const [imgRateLimitCD, setImgRateLimitCD] = useState(0);
  const [avatarRefFile, setAvatarRefFile] = useState<File | null>(null);
  const [bgRefFile, setBgRefFile] = useState<File | null>(null);
  const [cloneLoading, setCloneLoading] = useState(false);
  const [genAvatarRefLoading, setGenAvatarRefLoading] = useState(false);
  const [genBgRefLoading, setGenBgRefLoading] = useState(false);
  const [avatarOptions, setAvatarOptions] = useState<ImageOption[]>([]);
  const [bgOptions, setBgOptions] = useState<ImageOption[]>([]);
  const [selectAvatarLoading, setSelectAvatarLoading] = useState(false);
  const [selectBgLoading, setSelectBgLoading] = useState(false);
  const [promptGenLoading, setPromptGenLoading] = useState<"avatar" | "bg" | null>(null);
  const [previewImage, setPreviewImage] = useState<{ type: "avatar" | "bg"; url: string } | null>(null);
  const [cropTarget, setCropTarget] = useState<{ type: "avatar" | "bg"; src: string } | null>(null);
  const [cropping, setCropping] = useState(false);
  const [healthResult, setHealthResult] = useState<HealthCheckResult | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [pinnedNotes, setPinnedNotes] = useState<PinnedNote[]>([]);
  const [pinnedNotesLoading, setPinnedNotesLoading] = useState(false);
  const [rewriteLoading, setRewriteLoading] = useState(false);
  const [rewriteNicknameOptions, setRewriteNicknameOptions] = useState<string[]>([]);
  const [nicknameOptions, setNicknameOptions] = useState<string[]>([]);
  const [bioOptions, setBioOptions] = useState<string[]>([]);
  const [optionsLoading, setOptionsLoading] = useState<"nickname" | "bio" | null>(null);
  const [baseline, setBaseline] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<ProfileHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [restoringHistoryId, setRestoringHistoryId] = useState<string | null>(null);

  // ---- color presets ----
  const [colorPresets, setColorPresets] = useState<ColorSchemePreset[]>([]);

  // ============================================================
  // Load profile
  // ============================================================

  const loadProfile = useCallback(async () => {
    try {
      const res = await profileService.get(shopId, plat);
      const p = res.data;
      setVersion(p.version);
      setState({
        nickname: p.nickname || "",
        bio: p.bio || "",
        colorPrimary: p.color_primary || "#C93828",
        colorSecondary: p.color_secondary || "#FFF0EE",
        colorAccent: p.color_accent || "#A82015",
        colorText: p.color_text || "#2A0A08",
        colorMode: (p.color_mode as "preset" | "custom") || "preset",
        colorPresetName: p.color_preset_name || "江湖红",
        avatarUrl: p.avatar_url,
        avatarOriginalUrl: p.avatar_original_url,
        avatarPrompt: p.avatar_gen_prompt || "",
        bgImageUrl: p.bg_image_url,
        bgOriginalUrl: p.bg_original_url,
        bgPrompt: p.bg_gen_prompt || "",
        bioFlagged: p.bio_flagged,
        pinnedNotes: p.pinned_notes || [],
      });
      setAvatarOptions(p.avatar_options || []);
      setBgOptions(p.bg_options || []);
      setHealthResult(p.health_check || null);
      setPinnedNotes(p.pinned_notes || []);
      setBaseline(JSON.stringify({
        nickname: p.nickname || "",
        bio: p.bio || "",
        avatarPrompt: p.avatar_gen_prompt || "",
        bgPrompt: p.bg_gen_prompt || "",
        pinnedNotes: p.pinned_notes || [],
        colorPrimary: p.color_primary || "#C93828",
        colorSecondary: p.color_secondary || "#FFF0EE",
        colorAccent: p.color_accent || "#A82015",
        colorText: p.color_text || "#2A0A08",
      }));
      if (p.ai_variants?.variants) {
        setVariants(p.ai_variants.variants.filter((v) => !v.filtered));
      }
    } catch {
      message.error("加载装修数据失败");
    } finally {
      setLoading(false);
    }
  }, [shopId, plat]);

  useEffect(() => {
    loadProfile();
    profileService.getColorSchemes().then((res) => setColorPresets(res.data)).catch(() => {});
  }, [loadProfile]);

  const currentDirtyKey = JSON.stringify({
    nickname: state.nickname,
    bio: state.bio,
    avatarPrompt: state.avatarPrompt,
    bgPrompt: state.bgPrompt,
    pinnedNotes: state.pinnedNotes,
    colorPrimary: state.colorPrimary,
    colorSecondary: state.colorSecondary,
    colorAccent: state.colorAccent,
    colorText: state.colorText,
  });
  const dirty = baseline !== "" && baseline !== currentDirtyKey;

  const healthStale = !!healthResult?.snapshot && (
    state.nickname !== healthResult.snapshot.nickname ||
    state.bio !== healthResult.snapshot.bio ||
    state.avatarPrompt !== healthResult.snapshot.avatar_prompt ||
    state.bgPrompt !== healthResult.snapshot.bg_prompt ||
    state.colorPrimary !== healthResult.snapshot.color_primary ||
    state.colorSecondary !== healthResult.snapshot.color_secondary ||
    state.colorAccent !== healthResult.snapshot.color_accent ||
    state.colorText !== healthResult.snapshot.color_text ||
    JSON.stringify(state.pinnedNotes) !== JSON.stringify(healthResult.snapshot.pinned_notes || [])
  );

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // ============================================================
  // Save draft
  // ============================================================

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await profileService.update(shopId, plat, {
        nickname: state.nickname,
        bio: state.bio,
        avatar_gen_prompt: state.avatarPrompt,
        bg_gen_prompt: state.bgPrompt,
        pinned_notes: state.pinnedNotes,
        color_primary: state.colorPrimary,
        color_secondary: state.colorSecondary,
        color_accent: state.colorAccent,
        color_text: state.colorText,
        color_mode: state.colorMode,
        color_preset_name: state.colorPresetName,
        version,
      });
      setVersion(res.data.version);
      setState((s) => ({ ...s, bioFlagged: res.data.bio_flagged }));
      setBaseline(JSON.stringify({
        nickname: state.nickname,
        bio: state.bio,
        avatarPrompt: state.avatarPrompt,
        bgPrompt: state.bgPrompt,
        pinnedNotes: state.pinnedNotes,
        colorPrimary: state.colorPrimary,
        colorSecondary: state.colorSecondary,
        colorAccent: state.colorAccent,
        colorText: state.colorText,
      }));
      message.success("保存成功");
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 409) {
        message.warning("数据已被他人修改，正在刷新...");
        setTimeout(() => loadProfile(), 500);
      } else if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      } else {
        message.error("保存失败");
      }
    } finally {
      setSaving(false);
    }
  };

  // ============================================================
  // AI Generate
  // ============================================================

  const handleGenerate = async () => {
    if (rateLimitCD > 0) return;
    setGenerating(true);
    try {
      const res = await profileService.generate(shopId, plat, {
        category: genCategory,
        style: genStyle,
        price_range: genPrice,
      });
      const active = res.data.variants.filter((v) => !v.filtered);
      setVariants(active);
      if (active.length === 0) {
        message.warning("当前方案均未通过内容审核，请调整关键词后重试");
      } else if (active.length < res.data.variants.length) {
        message.info(`已生成 ${active.length} 套方案（${res.data.variants.length - active.length} 套未通过审核）`);
      } else {
        message.success(`已生成 ${active.length} 套方案`);
      }
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else if (err.response?.status === 422) {
        message.error("输入包含敏感词，请修改后重试");
      } else {
        message.error("生成失败，请重试");
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleGeneratePrompt = async (type: "avatar" | "bg") => {
    if (rateLimitCD > 0) return;
    setPromptGenLoading(type);
    try {
      const res = await profileService.generatePrompt(shopId, plat, {
        section: type,
        category: genCategory,
        style: genStyle,
        price_range: genPrice,
      });
      const key = type === "avatar" ? "avatarPrompt" : "bgPrompt";
      setState((s) => ({ ...s, [key]: res.data.prompt }));
      message.success(type === "avatar" ? "头像提示词已生成" : "背景提示词已生成");
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else if (err.response?.status === 422) {
        message.error("输入包含敏感词，请修改后重试");
      } else {
        message.error("提示词生成失败，请重试");
      }
    } finally {
      setPromptGenLoading(null);
    }
  };

  const applyVariant = (v: AiVariant) => {
    setState((s) => ({
      ...s,
      nickname: v.nickname_options[0] || "",
      bio: v.bio,
      bioFlagged: v.bio_flagged,
      colorPrimary: v.color_scheme.primary,
      colorSecondary: v.color_scheme.secondary,
      colorAccent: v.color_scheme.accent,
      colorText: v.color_scheme.text,
      colorMode: v.color_scheme.preset_name ? "preset" : "custom",
      colorPresetName: v.color_scheme.preset_name,
      avatarPrompt: v.avatar_prompt,
      bgPrompt: v.bg_prompt,
    }));
    message.success(`已应用方案 ${v.id}`);
  };

  // ============================================================
  // Image generate / upload
  // ============================================================

  const startImgRateLimitCountdown = () => {
    setImgRateLimitCD(30);
    message.warning("操作频繁，请 30 秒后重试");
    const timer = setInterval(() => {
      setImgRateLimitCD((c) => {
        if (c <= 1) { clearInterval(timer); return 0; }
        return c - 1;
      });
    }, 1000);
  };

  const waitForJob = async (jobId: string) => {
    for (let i = 0; i < 120; i += 1) {
      await new Promise((r) => setTimeout(r, 3000));
      const res = await profileService.getImageJob(shopId, plat, jobId);
      const job = res.data;
      if (job.status === "success") return job;
      if (job.status === "failed") throw new Error(job.error || "生图失败");
    }
    throw new Error("生图超时，请稍后刷新查看候选图");
  };

  const handleGenImage = async (type: "avatar" | "bg") => {
    if (imgRateLimitCD > 0) return;
    const prompt = type === "avatar" ? state.avatarPrompt : state.bgPrompt;
    if (!prompt) { message.warning("请先生成方案获取提示词，或手动输入"); return; }

    const setter = type === "avatar" ? setGenAvatarLoading : setGenBgLoading;
    setter(true);
    const msgKey = `img-${type}`;
    try {
      const createRes = await profileService.createImageJob(shopId, plat, type, prompt);
      message.loading({
        key: msgKey,
        content: `${type === "avatar" ? "头像" : "背景图"}生成中，约 1-2 分钟，可先做其他操作`,
        duration: 0,
      });
      const job = await waitForJob(createRes.data.job_id);
      const options = job.options || [];
      const url = options[0]?.url || "";
      const urlKey = type === "avatar" ? "avatarOriginalUrl" : "bgOriginalUrl";
      const urlKey2 = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      setState((s) => ({ ...s, [urlKey]: url, [urlKey2]: url }));
      if (type === "avatar") setAvatarOptions(options);
      else setBgOptions(options);
      message.success({ key: msgKey, content: `${type === "avatar" ? "头像" : "背景图"}生成成功` });
    } catch (e: unknown) {
      message.destroy(msgKey);
      const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (err.response?.status === 429) {
        startImgRateLimitCountdown();
      } else if (err.response?.status === 422) {
        message.error("提示词包含敏感词，请修改后重试");
      } else {
        message.error(err.message || `${type === "avatar" ? "头像" : "背景图"}生成失败`);
      }
    } finally {
      setter(false);
    }
  };

  const handleUpload = async (type: "avatar" | "bg", file: File) => {
    try {
      const fn = type === "avatar" ? profileService.uploadAvatar : profileService.uploadBgImage;
      const res = await fn(shopId, plat, file);
      const urlKey = type === "avatar" ? "avatarOriginalUrl" : "bgOriginalUrl";
      const urlKey2 = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      setState((s) => ({ ...s, [urlKey]: res.data.url, [urlKey2]: res.data.url }));
      if (type === "avatar") setAvatarOptions([]);
      else setBgOptions([]);
      message.success("上传成功");
    } catch {
      message.error("上传失败");
    }
    return false; // prevent default upload
  };

  const handleGenWithRef = async (type: "avatar" | "bg") => {
    if (imgRateLimitCD > 0) return;
    const prompt = type === "avatar" ? state.avatarPrompt : state.bgPrompt;
    if (!prompt) { message.warning("请先填写生图提示词"); return; }
    const refFile = type === "avatar" ? avatarRefFile : bgRefFile;
    if (!refFile) { message.warning("请先上传锚点图"); return; }

    const setter = type === "avatar" ? setGenAvatarRefLoading : setGenBgRefLoading;
    setter(true);
    const msgKey = `img-ref-${type}`;
    try {
      const createRes = await profileService.createImageJobWithRef(shopId, plat, type, prompt, refFile);
      message.loading({
        key: msgKey,
        content: `${type === "avatar" ? "头像" : "背景图"}锚点生图进行中，约 1-2 分钟`,
        duration: 0,
      });
      const job = await waitForJob(createRes.data.job_id);
      const options = job.options || [];
      const url = options[0]?.url || "";
      const urlKey = type === "avatar" ? "avatarOriginalUrl" : "bgOriginalUrl";
      const urlKey2 = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      setState((s) => ({ ...s, [urlKey]: url, [urlKey2]: url }));
      if (type === "avatar") setAvatarOptions(options);
      else setBgOptions(options);
      message.success({ key: msgKey, content: `${type === "avatar" ? "头像" : "背景图"}锚点生图成功` });
    } catch (e: unknown) {
      message.destroy(msgKey);
      const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (err.response?.status === 429) {
        startImgRateLimitCountdown();
      } else if (err.response?.status === 422) {
        message.error("提示词包含敏感词，请修改后重试");
      } else {
        message.error(err.message || `${type === "avatar" ? "头像" : "背景图"}锚点生图失败`);
      }
    } finally {
      setter(false);
    }
  };

  const handleSelectImage = async (type: "avatar" | "bg", option: ImageOption) => {
    const setter = type === "avatar" ? setSelectAvatarLoading : setSelectBgLoading;
    setter(true);
    try {
      const fn = type === "avatar"
        ? profileService.selectAvatar
        : profileService.selectBgImage;
      const res = await fn(shopId, plat, option.object_name);
      const urlKey = type === "avatar" ? "avatarOriginalUrl" : "bgOriginalUrl";
      const urlKey2 = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      const optionSetter = type === "avatar" ? setAvatarOptions : setBgOptions;
      setState((s) => ({ ...s, [urlKey]: res.data.url, [urlKey2]: res.data.url }));
      optionSetter((prev) =>
        prev.map((o) =>
          o.object_name === option.object_name ? { ...o, url: res.data.url } : o
        )
      );
      message.success(`${type === "avatar" ? "头像" : "背景图"}已选择`);
    } catch {
      message.error(`${type === "avatar" ? "头像" : "背景图"}选择失败`);
    } finally {
      setter(false);
    }
  };

  const handleCloneStyle = async (file: File) => {
    setCloneLoading(true);
    try {
      const res = await profileService.analyzeStyle(shopId, plat, file);
      const analysis: StyleAnalysis = res.data;
      const colors = (analysis.dominant_colors || [])
        .filter((c): c is string => !!c && /^#[0-9A-Fa-f]{6}$/.test(c));

      setState((s) => ({
        ...s,
        ...(colors.length === 4 ? {
          colorPrimary: colors[0],
          colorSecondary: colors[1],
          colorAccent: colors[2],
          colorText: colors[3],
          colorMode: "custom",
          colorPresetName: null,
        } : {}),
        ...(analysis.suggested_prompt ? {
          avatarPrompt: analysis.suggested_prompt,
          bgPrompt: analysis.suggested_prompt,
        } : {}),
      }));
      message.success(analysis.vibe ? `复刻完成：${analysis.vibe}` : "复刻完成，配色和提示词已应用");
    } catch {
      message.error("风格分析失败，请换一张更清晰的主页截图");
    } finally {
      setCloneLoading(false);
    }
  };

  const handleHealthCheck = async () => {
    if (rateLimitCD > 0) return;
    setHealthLoading(true);
    try {
      const res = await profileService.healthCheck(shopId, plat, {
        nickname: state.nickname,
        bio: state.bio,
        avatar_prompt: state.avatarPrompt,
        bg_prompt: state.bgPrompt,
        pinned_notes: state.pinnedNotes,
        color_primary: state.colorPrimary,
        color_secondary: state.colorSecondary,
        color_accent: state.colorAccent,
        color_text: state.colorText,
        has_avatar: !!(state.avatarUrl || state.avatarOriginalUrl),
        has_bg: !!(state.bgImageUrl || state.bgOriginalUrl),
      });
      setHealthResult(res.data);
      message.success("体检完成");
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else {
        message.error("体检失败，请重试");
      }
    } finally {
      setHealthLoading(false);
    }
  };

  const updatePinnedNote = (index: number, key: "title" | "content", value: string) => {
    setPinnedNotes((prev) => prev.map((n, i) => (i === index ? { ...n, [key]: value } : n)));
  };

  const removePinnedNote = (index: number) => {
    setPinnedNotes((prev) => prev.filter((_, i) => i !== index));
  };

  const handleGeneratePinnedNotes = async () => {
    if (rateLimitCD > 0) return;
    setPinnedNotesLoading(true);
    try {
      const res = await profileService.generatePinnedNotes(shopId, plat, {
        category: genCategory,
        style: genStyle,
        price_range: genPrice,
      });
      const notes = res.data.notes || [];
      setPinnedNotes((prev) => [...prev, ...notes].slice(0, 3));
      message.success(`已生成 ${notes.length} 条置顶候选`);
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else {
        message.error("置顶笔记生成失败，请重试");
      }
    } finally {
      setPinnedNotesLoading(false);
    }
  };

  const handleRewriteByHealthCheck = async () => {
    if (!healthResult || rateLimitCD > 0) return;
    setRewriteLoading(true);
    try {
      const res = await profileService.rewriteByHealthCheck(shopId, plat, {
        nickname: state.nickname,
        bio: state.bio,
        pinned_notes: state.pinnedNotes,
        weaknesses: healthResult.weaknesses,
        suggestions: healthResult.suggestions,
        category: genCategory,
        style: genStyle,
        price_range: genPrice,
      });
      setRewriteNicknameOptions(res.data.nickname_options || []);
      setState((s) => ({ ...s, bio: res.data.bio, bioFlagged: res.data.bio_flagged }));
      if (res.data.pinned_notes.length) setPinnedNotes(res.data.pinned_notes);
      message.success("已按体检建议更新简介和置顶笔记，昵称候选可点选");
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else {
        message.error("应用建议失败，请重试");
      }
    } finally {
      setRewriteLoading(false);
    }
  };

  const handleGenerateOptions = async (kind: "nickname" | "bio") => {
    if (rateLimitCD > 0) return;
    setOptionsLoading(kind);
    try {
      const res = await profileService.generateProfileOptions(shopId, plat, kind, {
        category: genCategory,
        style: genStyle,
        price_range: genPrice,
      });
      const options = res.data.options || [];
      if (kind === "nickname") {
        setNicknameOptions(options);
        message.success(options.length ? "昵称候选已生成" : "昵称候选未通过内容审核");
      } else {
        setBioOptions(options);
        message.success(options.length ? "简介候选已生成" : "简介候选未通过内容审核");
      }
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        setRateLimitCD(20);
        message.warning("操作频繁，请 20 秒后重试");
        const timer = setInterval(() => {
          setRateLimitCD((c) => { if (c <= 1) { clearInterval(timer); return 0; } return c - 1; });
        }, 1000);
      } else {
        message.error(kind === "nickname" ? "昵称候选生成失败" : "简介候选生成失败");
      }
    } finally {
      setOptionsLoading(null);
    }
  };

  const openHistory = async () => {
    setHistoryOpen(true);
    setHistoryLoading(true);
    try {
      const res = await profileService.getHistory(shopId, plat);
      setHistoryItems(res.data || []);
    } catch {
      message.error("历史版本加载失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const restoreHistory = (item: ProfileHistoryItem) => {
    Modal.confirm({
      title: `恢复 v${item.version} 版本`,
      content: `将用 ${new Date(item.created_at).toLocaleString("zh-CN")} 保存的内容覆盖当前草稿，确定恢复吗？`,
      okText: "恢复",
      cancelText: "取消",
      onOk: async () => {
        setRestoringHistoryId(item.id);
        try {
          await profileService.restoreHistory(shopId, plat, item.id);
          message.success("已恢复，正在刷新");
          setHistoryOpen(false);
          await loadProfile();
          await openHistory();
        } catch {
          message.error("恢复失败");
        } finally {
          setRestoringHistoryId(null);
        }
      },
    });
  };

  // ============================================================
  // Crop / remove / preview
  // ============================================================

  const openCrop = (type: "avatar" | "bg") => {
    const src = type === "avatar"
      ? state.avatarOriginalUrl || state.avatarUrl
      : state.bgOriginalUrl || state.bgImageUrl;
    if (!src) {
      message.warning("请先生成或上传图片");
      return;
    }
    setCropTarget({ type, src });
  };

  const handleCropConfirm = async (type: "avatar" | "bg", dataUrl: string) => {
    setCropping(true);
    try {
      const fn = type === "avatar" ? profileService.cropAvatar : profileService.cropBgImage;
      const res = await fn(shopId, plat, dataUrl);
      const urlKey = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      setState((s) => ({ ...s, [urlKey]: res.data.url }));
      setCropTarget(null);
      setPreviewImage(null);
      message.success("裁剪成功");
    } catch {
      message.error("裁剪失败");
    } finally {
      setCropping(false);
    }
  };

  const handleRemoveImage = async (type: "avatar" | "bg", option: ImageOption) => {
    try {
      const res = await profileService.removeGalleryImage(shopId, plat, type, option.object_name);
      const optionSetter = type === "avatar" ? setAvatarOptions : setBgOptions;
      optionSetter(res.data || []);
      const originalKey = type === "avatar" ? "avatarOriginalUrl" : "bgOriginalUrl";
      const displayKey = type === "avatar" ? "avatarUrl" : "bgImageUrl";
      setState((s) => {
        if (sameObject(s[originalKey], option.url) || sameObject(s[displayKey], option.url)) {
          return { ...s, [originalKey]: null, [displayKey]: null };
        }
        return s;
      });
      setPreviewImage((cur) =>
        cur && sameObject(cur.url, option.url) ? null : cur
      );
      message.success("已移除");
    } catch {
      message.error("移除失败");
    }
  };

  const handleSetCurrentFromPreview = async () => {
    if (!previewImage) return;
    const option =
      (previewImage.type === "avatar" ? avatarOptions : bgOptions).find((o) =>
        sameObject(o.url, previewImage.url)
      );
    if (!option) {
      message.warning("该图片不在当前生成结果中");
      return;
    }
    await handleSelectImage(previewImage.type, option);
    setPreviewImage(null);
  };

  // ============================================================
  // Copy all
  // ============================================================

  const handleCopyAll = () => {
    if (state.bioFlagged) {
      Modal.confirm({
        title: "简介未通过内容审核",
        content: "简介未通过内容审核，是否仍要复制？",
        okText: "仍要复制",
        cancelText: "取消",
        onOk: () => doCopy(),
      });
    } else {
      doCopy();
    }
  };

  const doCopy = async () => {
    const text = `昵称：${state.nickname}\n简介：${state.bio}`;
    await navigator.clipboard.writeText(text);
    message.success("已复制到剪贴板");
  };

  // ============================================================
  // Render
  // ============================================================

  if (loading) return <div style={{ textAlign: "center", padding: 80 }}><Spin size="large" /></div>;

  return (
    <div>
      <Title level={4} style={{ marginBottom: 20 }}>
        平台账号装修 — {plat === "xiaohongshu" ? "小红书" : plat}
      </Title>

      <Row gutter={24}>
        {/* ====== Left Panel ====== */}
        <Col xs={24} lg={14}>
          {/* Color Scheme */}
          <Card title="色系方案" size="small" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              {colorPresets.map((c) => (
                <Tooltip key={c.name} title={c.description}>
                  <div
                    onClick={() => {
                      setState((s) => ({
                        ...s,
                        colorPrimary: c.primary, colorSecondary: c.secondary,
                        colorAccent: c.accent, colorText: c.text,
                        colorMode: "preset", colorPresetName: c.name,
                      }));
                    }}
                    style={{
                      display: "flex", gap: 2, cursor: "pointer",
                      border: state.colorPresetName === c.name ? "2px solid #1677ff" : "2px solid transparent",
                      borderRadius: 6, padding: 2,
                    }}
                  >
                    {[c.primary, c.secondary, c.accent, c.text].map((clr, i) => (
                      <div key={i} style={{ width: 20, height: 20, borderRadius: 3, background: clr }} />
                    ))}
                  </div>
                </Tooltip>
              ))}
            </div>
            <Space wrap>
              <ColorPicker
                value={state.colorPrimary}
                onChange={(c: Color) => setState((s) => ({ ...s, colorPrimary: c.toHexString(), colorMode: "custom", colorPresetName: null }))}
              />
              <Text type="secondary">主色</Text>
              <ColorPicker
                value={state.colorSecondary}
                onChange={(c: Color) => setState((s) => ({ ...s, colorSecondary: c.toHexString(), colorMode: "custom", colorPresetName: null }))}
              />
              <Text type="secondary">辅色</Text>
              <ColorPicker
                value={state.colorAccent}
                onChange={(c: Color) => setState((s) => ({ ...s, colorAccent: c.toHexString(), colorMode: "custom", colorPresetName: null }))}
              />
              <Text type="secondary">点缀</Text>
              <ColorPicker
                value={state.colorText}
                onChange={(c: Color) => setState((s) => ({ ...s, colorText: c.toHexString(), colorMode: "custom", colorPresetName: null }))}
              />
              <Text type="secondary">文字</Text>
            </Space>
          </Card>

          {/* AI Generate */}
          <Card
            title={<span><ThunderboltOutlined /> AI 智能生成</span>}
            size="small"
            style={{ marginBottom: 16 }}
          >
            <Space wrap style={{ marginBottom: 12 }}>
              <Input
                placeholder="品类" value={genCategory}
                onChange={(e) => setGenCategory(e.target.value)}
                style={{ width: 100 }}
              />
              <Input
                placeholder="风格" value={genStyle}
                onChange={(e) => setGenStyle(e.target.value)}
                style={{ width: 140 }}
              />
              <Input
                placeholder="价格" value={genPrice}
                onChange={(e) => setGenPrice(e.target.value)}
                style={{ width: 100 }}
              />
              <Button
                type="primary" icon={<ThunderboltOutlined />}
                loading={generating}
                disabled={rateLimitCD > 0}
                onClick={handleGenerate}
              >
                {rateLimitCD > 0 ? `${rateLimitCD}s 后重试` : "生成装修方案"}
              </Button>
            </Space>

            {variants.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
                {variants.map((v) => (
                  <Card
                    key={v.id}
                    size="small"
                    hoverable
                    onClick={() => applyVariant(v)}
                    style={{ cursor: "pointer" }}
                  >
                    <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                      {[v.color_scheme.primary, v.color_scheme.secondary, v.color_scheme.accent].map((c, i) => (
                        <div key={i} style={{ width: 16, height: 16, borderRadius: 3, background: c }} />
                      ))}
                      <Text style={{ fontSize: 12, marginLeft: 4 }}>{v.color_scheme.preset_name || "自定义"}</Text>
                    </div>
                    <Text strong style={{ fontSize: 12 }}>方案 {v.id}</Text>
                    <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>
                      {v.nickname_options.slice(0, 2).map((n, i) => (
                        <Tag key={i} style={{ marginBottom: 2, fontSize: 10 }}>{n}</Tag>
                      ))}
                    </div>
                    <Paragraph
                      style={{ fontSize: 11, color: "#999", marginBottom: 0 }}
                      ellipsis={{ rows: 2 }}
                    >
                      {v.bio}
                    </Paragraph>
                  </Card>
                ))}
              </div>
            )}
          </Card>

          {/* Nickname */}
          <Card title="昵称" size="small" style={{ marginBottom: 16 }}>
            <Input
              value={state.nickname}
              onChange={(e) => setState((s) => ({ ...s, nickname: e.target.value }))}
              maxLength={20}
              suffix={<Text type="secondary">{state.nickname.length}/20</Text>}
            />
            <Space style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>候选昵称：</Text>
              <Button size="small" icon={<EditOutlined />} loading={optionsLoading === "nickname"} disabled={rateLimitCD > 0} onClick={() => handleGenerateOptions("nickname")}>
                AI 建议
              </Button>
            </Space>
            {(state.nickname.length > 0 || nicknameOptions.length > 0) && (
              <div style={{ marginTop: 4 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                  {[...new Set([...nicknameOptions, ...variants.flatMap((v) => v.nickname_options)])].slice(0, 12).map((n, i) => (
                    <Tag
                      key={i}
                      color={n === state.nickname ? "blue" : undefined}
                      style={{ cursor: "pointer" }}
                      onClick={() => setState((s) => ({ ...s, nickname: n }))}
                    >
                      {n}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Bio */}
          <Card title="简介" size="small" style={{ marginBottom: 16 }}>
            <TextArea
              value={state.bio}
              onChange={(e) => setState((s) => ({ ...s, bio: e.target.value }))}
              maxLength={100}
              rows={3}
              placeholder="输入简介文案（支持 emoji）"
            />
            <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{state.bio.length}/100</Text>
                {state.bioFlagged && <Tag color="error">内容待审核</Tag>}
              </Space>
              <Button size="small" icon={<EditOutlined />} loading={optionsLoading === "bio"} disabled={rateLimitCD > 0} onClick={() => handleGenerateOptions("bio")}>
                AI 建议
              </Button>
            </div>
            {bioOptions.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>简介候选：</Text>
                {bioOptions.map((b, i) => (
                  <div
                    key={i}
                    onClick={() => setState((s) => ({ ...s, bio: b }))}
                    style={{ marginTop: 4, padding: "6px 8px", borderRadius: 6, border: "1px solid #eee", cursor: "pointer", fontSize: 12, whiteSpace: "pre-wrap" }}
                  >
                    {b}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Pinned Notes */}
          <Card title="置顶笔记" size="small" style={{ marginBottom: 16 }}>
            {pinnedNotes.map((note, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <Input
                    placeholder="置顶标题（20 字内）"
                    maxLength={20}
                    value={note.title}
                    onChange={(e) => updatePinnedNote(i, "title", e.target.value)}
                  />
                  <Input
                    placeholder="内容（80 字内）"
                    maxLength={80}
                    style={{ marginTop: 4 }}
                    value={note.content}
                    onChange={(e) => updatePinnedNote(i, "content", e.target.value)}
                  />
                </div>
                <Button type="text" danger icon={<DeleteOutlined />} onClick={() => removePinnedNote(i)} />
              </div>
            ))}
            <Space wrap style={{ marginTop: 4 }}>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setPinnedNotes((s) => [...s, { title: "", content: "" }])}>
                添加置顶
              </Button>
              <Button size="small" icon={<EditOutlined />} loading={pinnedNotesLoading} onClick={handleGeneratePinnedNotes}>
                AI 生成候选
              </Button>
            </Space>
            <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 6 }}>
              最多 3 条，展示在小红书预览下方
            </Text>
          </Card>

          {/* Avatar */}
          <Card title="头像" size="small" style={{ marginBottom: 16 }}>
            <Space wrap>
              <div style={{
                width: 60, height: 60, borderRadius: "50%",
                background: (state.avatarUrl || state.avatarOriginalUrl) ? `url(${state.avatarUrl || state.avatarOriginalUrl}) center/cover` : "#ddd",
                border: "1px solid #eee",
              }} />
              <Upload
                accept="image/png,image/jpeg,image/webp"
                showUploadList={false}
                beforeUpload={(f) => { handleUpload("avatar", f); return false; }}
              >
                <Button icon={<UploadOutlined />}>上传</Button>
              </Upload>
              <Button
                icon={<PictureOutlined />}
                loading={genAvatarLoading}
                disabled={imgRateLimitCD > 0}
                onClick={() => handleGenImage("avatar")}
              >
                AI 生图{imgRateLimitCD > 0 ? ` (${imgRateLimitCD}s)` : ""}
              </Button>
              <Button icon={<ScissorOutlined />} onClick={() => openCrop("avatar")}>裁剪</Button>
              <Divider type="vertical" />
              <Upload accept="image/*" showUploadList={false} beforeUpload={(f) => { setAvatarRefFile(f); message.info("锚点图已选: " + f.name); return false; }}>
                <Button>{avatarRefFile ? avatarRefFile.name.slice(0, 8) + "..." : "上传锚点图"}</Button>
              </Upload>
              <Button
                icon={<PictureOutlined />}
                loading={genAvatarRefLoading}
                onClick={() => handleGenWithRef("avatar")}
              >
                锚点生图
              </Button>
            </Space>
            <div style={{ position: "relative", marginTop: 8 }}>
              <TextArea
                rows={2}
                placeholder="生图提示词（中文）"
                value={state.avatarPrompt}
                onChange={(e) => setState((s) => ({ ...s, avatarPrompt: e.target.value }))}
                style={{ paddingBottom: 28, paddingRight: 118 }}
              />
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                loading={promptGenLoading === "avatar"}
                disabled={rateLimitCD > 0}
                onClick={() => handleGeneratePrompt("avatar")}
                style={{ position: "absolute", right: 6, bottom: 4, fontSize: 12 }}
              >
                一键生成提示词
              </Button>
            </div>
            <ImageOptionsGrid
              options={avatarOptions}
              selectedUrl={state.avatarOriginalUrl}
              width={64}
              height={64}
              loading={selectAvatarLoading}
              onSelect={(o) => handleSelectImage("avatar", o)}
              onPreview={(o) => setPreviewImage({ type: "avatar", url: o.url })}
              onRemove={(o) => handleRemoveImage("avatar", o)}
            />
          </Card>

          {/* Bg Image */}
          <Card title="背景图" size="small" style={{ marginBottom: 16 }}>
            <Space wrap>
              <div style={{
                width: 112, height: 42, borderRadius: 4,
                background: (state.bgImageUrl || state.bgOriginalUrl) ? `url(${state.bgImageUrl || state.bgOriginalUrl}) center/cover` : "#ddd",
                border: "1px solid #eee",
              }} />
              <Upload
                accept="image/png,image/jpeg,image/webp"
                showUploadList={false}
                beforeUpload={(f) => { handleUpload("bg", f); return false; }}
              >
                <Button icon={<UploadOutlined />}>上传</Button>
              </Upload>
              <Button
                icon={<PictureOutlined />}
                loading={genBgLoading}
                disabled={imgRateLimitCD > 0}
                onClick={() => handleGenImage("bg")}
              >
                AI 生图{imgRateLimitCD > 0 ? ` (${imgRateLimitCD}s)` : ""}
              </Button>
              <Button icon={<ScissorOutlined />} onClick={() => openCrop("bg")}>裁剪</Button>
              <Divider type="vertical" />
              <Upload accept="image/*" showUploadList={false} beforeUpload={(f) => { setBgRefFile(f); message.info("锚点图已选: " + f.name); return false; }}>
                <Button>{bgRefFile ? bgRefFile.name.slice(0, 8) + "..." : "上传锚点图"}</Button>
              </Upload>
              <Button
                icon={<PictureOutlined />}
                loading={genBgRefLoading}
                onClick={() => handleGenWithRef("bg")}
              >
                锚点生图
              </Button>
            </Space>
            <div style={{ position: "relative", marginTop: 8 }}>
              <TextArea
                rows={2}
                placeholder="生图提示词（中文）"
                value={state.bgPrompt}
                onChange={(e) => setState((s) => ({ ...s, bgPrompt: e.target.value }))}
                style={{ paddingBottom: 28, paddingRight: 118 }}
              />
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                loading={promptGenLoading === "bg"}
                disabled={rateLimitCD > 0}
                onClick={() => handleGeneratePrompt("bg")}
                style={{ position: "absolute", right: 6, bottom: 4, fontSize: 12 }}
              >
                一键生成提示词
              </Button>
            </div>
            <ImageOptionsGrid
              options={bgOptions}
              selectedUrl={state.bgOriginalUrl}
              width={112}
              height={64}
              loading={selectBgLoading}
              onSelect={(o) => handleSelectImage("bg", o)}
              onPreview={(o) => setPreviewImage({ type: "bg", url: o.url })}
              onRemove={(o) => handleRemoveImage("bg", o)}
            />
          </Card>

          {/* Action Bar */}
          <Divider />
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
              size="large"
            >
              保存草稿
            </Button>
            <Button icon={<CopyOutlined />} onClick={handleCopyAll} size="large">
              一键复制全部文案
            </Button>
            <Button icon={<HistoryOutlined />} onClick={openHistory} size="large">
              历史版本
            </Button>
          </Space>
        </Col>

        {/* ====== Right Panel: Preview + 复刻同款 ====== */}
        <Col xs={24} lg={10}>
          <div style={{ position: "sticky", top: 24 }}>
            <Card
              title={<span><EyeOutlined /> 小红书预览</span>}
              size="small"
            >
              <PlatformPreview state={state} />
              <div style={{ marginTop: 12, padding: 8, background: "#fafafa", borderRadius: 4 }}>
                <Row gutter={[8, 4]}>
                  {[
                    { label: "主色", color: state.colorPrimary },
                    { label: "辅色", color: state.colorSecondary },
                    { label: "点缀", color: state.colorAccent },
                    { label: "文字", color: state.colorText },
                  ].map((c) => (
                    <Col span={12} key={c.label}>
                      <Space>
                        <div style={{ width: 14, height: 14, borderRadius: 3, background: c.color, border: "1px solid #ddd" }} />
                        <Text style={{ fontSize: 12 }}>{c.label}: {c.color}</Text>
                      </Space>
                    </Col>
                  ))}
                </Row>
              </div>
              <Divider style={{ margin: "12px 0" }} />
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <Text strong style={{ fontSize: 13 }}>
                    <AuditOutlined /> 主页体检
                  </Text>
                  <Button
                    size="small"
                    type="primary"
                    ghost
                    icon={<AuditOutlined />}
                    loading={healthLoading}
                    disabled={rateLimitCD > 0}
                    onClick={handleHealthCheck}
                  >
                    {rateLimitCD > 0 ? `${rateLimitCD}s 后重试` : "体检当前预览"}
                  </Button>
                  {healthResult && (
                    <Button
                      size="small"
                      type="primary"
                      icon={<CheckOutlined />}
                      loading={rewriteLoading}
                      disabled={rateLimitCD > 0}
                      onClick={handleRewriteByHealthCheck}
                    >
                      按建议优化
                    </Button>
                  )}
                </div>
                {healthResult && !healthLoading && (
                  <div style={{ fontSize: 12, color: "#555", lineHeight: 1.7 }}>
                    {healthStale && (
                      <Text type="warning" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
                        内容已修改，建议重新体检
                      </Text>
                    )}
                    <div style={{ padding: "8px 10px", background: "#f6f8ff", borderRadius: 6, marginBottom: 8 }}>
                      <Text strong style={{ fontSize: 12 }}>第一眼判断：</Text>
                      <span>{healthResult.first_impression}</span>
                    </div>
                    <HealthCheckBlock title="优点" color="#389e0d" items={healthResult.strengths} />
                    <HealthCheckBlock title="不足" color="#d4380d" items={healthResult.weaknesses} />
                    <HealthCheckBlock title="建议" color="#1677ff" items={healthResult.suggestions} />
                    {rewriteNicknameOptions.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <Text strong style={{ fontSize: 12 }}>优化昵称候选：</Text>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                          {rewriteNicknameOptions.map((n, i) => (
                            <Tag key={i} style={{ cursor: "pointer" }} color={n === state.nickname ? "blue" : undefined} onClick={() => setState((s) => ({ ...s, nickname: n }))}>
                              {n}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    )}
                    {healthResult.checked_at && (
                      <Text type="secondary" style={{ fontSize: 11, display: "block", marginTop: 6 }}>
                        体检时间：{new Date(healthResult.checked_at).toLocaleString("zh-CN")}
                      </Text>
                    )}
                  </div>
                )}
              </div>
              <Divider style={{ margin: "12px 0" }} />
              <div>
                <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
                  上传他人小红书主页截图，AI 分析风格并自动应用配色和提示词
                </Text>
                <Upload
                  accept="image/*"
                  showUploadList={false}
                  beforeUpload={(f) => { handleCloneStyle(f); return false; }}
                >
                  <Button loading={cloneLoading} block>
                    上传截图 · 一键复刻
                  </Button>
                </Upload>
              </div>
            </Card>
          </div>
        </Col>
      </Row>

      {/* 大图预览 / 裁剪弹窗 */}
      <ImagePreviewModal
        open={!!previewImage}
        src={previewImage?.url || null}
        title={previewImage?.type === "avatar" ? "头像预览" : "背景图预览"}
        onClose={() => setPreviewImage(null)}
        onSetCurrent={handleSetCurrentFromPreview}
        onCrop={() => {
          if (previewImage) {
            setCropTarget({ type: previewImage.type, src: previewImage.url });
            setPreviewImage(null);
          }
        }}
        onRemove={() => {
          if (previewImage) {
            const option =
              (previewImage.type === "avatar" ? avatarOptions : bgOptions).find((o) =>
                sameObject(o.url, previewImage.url)
              );
            if (option) handleRemoveImage(previewImage.type, option);
            setPreviewImage(null);
          }
        }}
      />
      <CropModal
        open={!!cropTarget}
        src={cropTarget?.src || null}
        title={cropTarget?.type === "avatar" ? "裁剪头像" : "裁剪背景图"}
        aspect={cropTarget?.type === "avatar" ? 1 : 375 / 140}
        targetWidth={cropTarget?.type === "avatar" ? 1024 : 1500}
        targetHeight={cropTarget?.type === "avatar" ? 1024 : 560}
        loading={cropping}
        onCancel={() => setCropTarget(null)}
        onConfirm={(dataUrl) => {
          if (cropTarget) handleCropConfirm(cropTarget.type, dataUrl);
        }}
      />

      {/* 历史版本 */}
      <Modal
        open={historyOpen}
        title="历史版本"
        onCancel={() => setHistoryOpen(false)}
        footer={null}
        width={640}
      >
        <Spin spinning={historyLoading}>
          {historyItems.length === 0 && !historyLoading && (
            <Text type="secondary">暂无历史版本，保存草稿后自动生成</Text>
          )}
          <div style={{ maxHeight: 420, overflow: "auto" }}>
            {historyItems.map((item) => (
              <div key={item.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid #f0f0f0" }}>
                <div style={{ minWidth: 0, flex: 1, marginRight: 12 }}>
                  <Space size={6}>
                    <Tag color="blue">v{item.version}</Tag>
                    <Text style={{ fontSize: 12, color: "#999" }}>
                      {new Date(item.created_at).toLocaleString("zh-CN")}
                    </Text>
                    {item.avatar_set && <Tag>头像</Tag>}
                    {item.bg_set && <Tag>背景</Tag>}
                  </Space>
                  <div style={{ fontSize: 12, marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <Text strong>{item.nickname || "未填昵称"}</Text>
                    <Text type="secondary"> · {item.bio || "未填简介"}</Text>
                  </div>
                </div>
                <Button size="small" type="primary" ghost loading={restoringHistoryId === item.id} onClick={() => restoreHistory(item)}>
                  恢复
                </Button>
              </div>
            ))}
          </div>
        </Spin>
      </Modal>
    </div>
  );
}

