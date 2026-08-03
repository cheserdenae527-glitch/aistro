import { useEffect, useRef, useState } from "react";
import { Button, Modal, Typography } from "antd";
import { ScissorOutlined } from "@ant-design/icons";

const { Text } = Typography;

export interface CropRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export default function CropModal({
  open,
  src,
  title,
  aspect,
  targetWidth,
  targetHeight,
  loading,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  src: string | null;
  title: string;
  aspect: number;
  targetWidth: number;
  targetHeight: number;
  loading: boolean;
  onCancel: () => void;
  onConfirm: (dataUrl: string, rect: CropRect) => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);
  const [rect, setRect] = useState<CropRect | null>(null);
  const [drag, setDrag] = useState<{
    mode: "draw" | "move";
    startX: number;
    startY: number;
    startRect: CropRect;
  } | null>(null);

  useEffect(() => {
    if (!open) {
      setNat(null);
      setRect(null);
      setDrag(null);
    }
  }, [open, src]);

  const handleLoad = () => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;
    const n = { w: img.naturalWidth, h: img.naturalHeight };
    setNat(n);
    let w = n.w * 0.8;
    let h = w / aspect;
    if (h > n.h * 0.8) {
      h = n.h * 0.8;
      w = h * aspect;
    }
    setRect({
      x: (n.w - w) / 2,
      y: Math.max(0, (n.h - h) / 2),
      w,
      h,
    });
  };

  const toNatural = (e: React.MouseEvent): { x: number; y: number } => {
    const img = imgRef.current;
    if (!img || !nat) return { x: 0, y: 0 };
    const b = img.getBoundingClientRect();
    return {
      x: ((e.clientX - b.left) / b.width) * nat.w,
      y: ((e.clientY - b.top) / b.height) * nat.h,
    };
  };

  const clampRect = (r: CropRect): CropRect => {
    if (!nat) return r;
    const w = Math.max(16, Math.min(r.w, nat.w));
    const h = Math.max(16, Math.min(r.h, nat.h));
    const x = Math.min(Math.max(0, r.x), nat.w - w);
    const y = Math.min(Math.max(0, r.y), nat.h - h);
    return { x, y, w, h };
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (!rect || !nat) return;
    const p = toNatural(e);
    const inside =
      p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h;
    setDrag({
      mode: inside ? "move" : "draw",
      startX: p.x,
      startY: p.y,
      startRect: rect,
    });
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag || !nat) return;
    const p = toNatural(e);
    if (drag.mode === "move") {
      setRect(
        clampRect({
          ...drag.startRect,
          x: drag.startRect.x + (p.x - drag.startX),
          y: drag.startRect.y + (p.y - drag.startY),
        })
      );
      return;
    }
    const dx = p.x - drag.startX;
    const dy = p.y - drag.startY;
    let w = Math.max(Math.abs(dx), Math.abs(dy) * aspect);
    w = Math.min(w, nat.w, nat.h * aspect);
    const h = w / aspect;
    const x = dx < 0 ? drag.startX - w : drag.startX;
    const y = dy < 0 ? drag.startY - h : drag.startY;
    setRect(clampRect({ x, y, w, h }));
  };

  const handleConfirm = () => {
    const img = imgRef.current;
    if (!img || !rect) return;
    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, targetWidth, targetHeight);
    onConfirm(canvas.toDataURL("image/jpeg", 0.92), rect);
  };

  return (
    <Modal
      open={open}
      title={title}
      onCancel={onCancel}
      width={700}
      confirmLoading={loading}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="ok"
          type="primary"
          icon={<ScissorOutlined />}
          disabled={!rect}
          onClick={handleConfirm}
        >
          应用裁剪
        </Button>,
      ]}
    >
      <div style={{ display: "flex", justifyContent: "center" }}>
        <div
          style={{
            position: "relative",
            display: "inline-block",
            overflow: "hidden",
            borderRadius: 6,
            cursor: drag ? "grabbing" : "crosshair",
            userSelect: "none",
          }}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={() => setDrag(null)}
          onMouseLeave={() => setDrag(null)}
        >
          <img
            ref={imgRef}
            src={src || undefined}
            alt="裁剪原图"
            onLoad={handleLoad}
            draggable={false}
            style={{ display: "block", maxWidth: "100%", maxHeight: 420 }}
          />
          {rect && nat && (
            <div
              style={{
                position: "absolute",
                left: `${(rect.x / nat.w) * 100}%`,
                top: `${(rect.y / nat.h) * 100}%`,
                width: `${(rect.w / nat.w) * 100}%`,
                height: `${(rect.h / nat.h) * 100}%`,
                border: "2px solid #fff",
                boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)",
                cursor: "move",
              }}
            />
          )}
        </div>
      </div>
      <Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 8, fontSize: 12 }}>
        {title}输出 {targetWidth}x{targetHeight}
      </Text>
    </Modal>
  );
}
