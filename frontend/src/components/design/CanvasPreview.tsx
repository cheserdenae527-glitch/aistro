import { useCallback, useEffect, useRef } from "react";
import type { EditorSettings } from "../../utils/editStack";
import { loadImageElement, renderToCanvas } from "../../utils/canvasRenderer";

export default function CanvasPreview({
  sourceUrl,
  settings,
  onImageLoad,
  style,
}: {
  sourceUrl: string;
  settings: EditorSettings;
  onImageLoad?: (w: number, h: number) => void;
  style?: React.CSSProperties;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    if (!canvas || !image) return;
    renderToCanvas(canvas, image, settings);
  }, [settings]);

  useEffect(() => {
    let alive = true;
    imageRef.current = null;
    loadImageElement(sourceUrl)
      .then((img) => {
        if (!alive) return;
        imageRef.current = img;
        onImageLoad?.(img.naturalWidth, img.naturalHeight);
        draw();
      })
      .catch(() => {
        imageRef.current = null;
      });
    return () => {
      alive = false;
    };
  }, [sourceUrl, draw, onImageLoad]);

  useEffect(() => {
    draw();
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: "100%",
        height: "auto",
        display: "block",
        borderRadius: 8,
        background: "#fff",
        boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
        ...style,
      }}
    />
  );
}
