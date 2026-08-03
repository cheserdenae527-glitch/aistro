import type { EditorSettings } from "./editStack";

export function buildFilterChain(settings: EditorSettings): string[] {
  const filters: string[] = [];
  if (settings.brightness !== 100) {
    filters.push(`brightness(${(settings.brightness / 100).toFixed(3)})`);
  }
  if (settings.contrast !== 100) {
    filters.push(`contrast(${(settings.contrast / 100).toFixed(3)})`);
  }
  if (settings.saturation !== 100) {
    filters.push(`saturate(${(settings.saturation / 100).toFixed(3)})`);
  }
  switch (settings.filter) {
    case "warm":
      filters.push("saturate(1.15) sepia(0.18) contrast(1.06)");
      break;
    case "japanese":
      filters.push("saturate(0.88) brightness(1.06) contrast(0.96) hue-rotate(-6deg)");
      break;
    case "vivid":
      filters.push("saturate(1.35) contrast(1.1)");
      break;
    case "bw":
      filters.push("grayscale(1) contrast(1.05)");
      break;
    default:
      break;
  }
  return filters;
}

export function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const tryLoad = (crossOrigin: boolean) => {
      const img = new Image();
      if (crossOrigin) img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = () => {
        if (crossOrigin) {
          tryLoad(false);
        } else {
          reject(new Error("图片加载失败"));
        }
      };
      img.src = src;
    };
    tryLoad(true);
  });
}

export function cropSource(settings: EditorSettings, naturalWidth: number, naturalHeight: number) {
  if (!settings.crop) {
    return { sx: 0, sy: 0, sw: naturalWidth, sh: naturalHeight };
  }
  return {
    sx: settings.crop.x,
    sy: settings.crop.y,
    sw: settings.crop.w,
    sh: settings.crop.h,
  };
}

export function outputSize(settings: EditorSettings, naturalWidth: number, naturalHeight: number) {
  const { sw, sh } = cropSource(settings, naturalWidth, naturalHeight);
  const rotation = ((settings.rotation % 360) + 360) % 360;
  return rotation === 90 || rotation === 270
    ? { width: Math.round(sh), height: Math.round(sw) }
    : { width: Math.round(sw), height: Math.round(sh) };
}

export function renderToCanvas(
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  settings: EditorSettings,
  options: { includeTexts?: boolean } = {}
): void {
  const naturalWidth = image.naturalWidth || 1;
  const naturalHeight = image.naturalHeight || 1;
  const { sx, sy, sw, sh } = cropSource(settings, naturalWidth, naturalHeight);
  const rotation = ((settings.rotation % 360) + 360) % 360;
  const { width, height } = outputSize(settings, naturalWidth, naturalHeight);

  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, width, height);

  ctx.save();
  const filters = buildFilterChain(settings);
  if (filters.length > 0) ctx.filter = filters.join(" ");
  ctx.translate(width / 2, height / 2);
  ctx.rotate((rotation * Math.PI) / 180);
  ctx.drawImage(image, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
  ctx.restore();

  if (settings.temperature !== 0) {
    ctx.save();
    ctx.globalCompositeOperation = "overlay";
    ctx.globalAlpha = Math.min(0.32, (Math.abs(settings.temperature) / 100) * 0.28);
    ctx.fillStyle = settings.temperature > 0 ? "rgb(255,150,40)" : "rgb(40,120,255)";
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  }

  if (options.includeTexts) {
    for (const label of settings.texts) {
      const fontSize = Math.max(10, height * (label.size / 100));
      ctx.font = `600 ${fontSize}px "Noto Sans SC", "Microsoft YaHei", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineWidth = Math.max(2, fontSize / 8);
      ctx.strokeStyle = "rgba(0,0,0,0.65)";
      ctx.strokeText(label.text, label.x * width, label.y * height);
      ctx.fillStyle = label.color;
      ctx.fillText(label.text, label.x * width, label.y * height);
    }
  }
}
