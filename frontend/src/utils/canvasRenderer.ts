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
  const strength = Math.min(1, Math.max(0, settings.filterStrength / 100));
  switch (settings.filter) {
    case "warm":
      filters.push(
        `saturate(${(1 + 0.15 * strength).toFixed(3)}) sepia(${(0.18 * strength).toFixed(3)}) contrast(${(1 + 0.06 * strength).toFixed(3)})`
      );
      break;
    case "japanese":
      filters.push(
        `saturate(${(1 - 0.12 * strength).toFixed(3)}) brightness(${(1 + 0.06 * strength).toFixed(3)}) contrast(${(1 - 0.04 * strength).toFixed(3)}) hue-rotate(${(-6 * strength).toFixed(2)}deg)`
      );
      break;
    case "vivid":
      filters.push(
        `saturate(${(1 + 0.35 * strength).toFixed(3)}) contrast(${(1 + 0.1 * strength).toFixed(3)})`
      );
      break;
    case "bw":
      filters.push(
        `grayscale(${strength.toFixed(3)}) contrast(${(1 + 0.05 * strength).toFixed(3)})`
      );
      break;
    case "film":
      filters.push(
        `sepia(${(0.35 * strength).toFixed(3)}) saturate(${(1 + 0.15 * strength).toFixed(3)}) contrast(${(1 + 0.05 * strength).toFixed(3)}) brightness(${(1 - 0.03 * strength).toFixed(3)})`
      );
      break;
    case "tealOrange":
      filters.push(
        `contrast(${(1 + 0.1 * strength).toFixed(3)}) saturate(${(1 + 0.35 * strength).toFixed(3)}) sepia(${(0.25 * strength).toFixed(3)}) hue-rotate(${(-12 * strength).toFixed(2)}deg)`
      );
      break;
    case "cool":
      filters.push(
        `brightness(${(1 + 0.02 * strength).toFixed(3)}) contrast(${(1 + 0.04 * strength).toFixed(3)}) saturate(${(1 - 0.05 * strength).toFixed(3)}) hue-rotate(${(8 * strength).toFixed(2)}deg)`
      );
      break;
    case "soft":
      filters.push(
        `brightness(${(1 + 0.06 * strength).toFixed(3)}) contrast(${(1 - 0.08 * strength).toFixed(3)}) saturate(${(1 + 0.05 * strength).toFixed(3)})`
      );
      break;
    case "moody":
      filters.push(
        `brightness(${(1 - 0.1 * strength).toFixed(3)}) contrast(${(1 + 0.15 * strength).toFixed(3)}) saturate(${(1 - 0.1 * strength).toFixed(3)})`
      );
      break;
    case "fresh":
      filters.push(
        `saturate(${(1 + 0.1 * strength).toFixed(3)}) brightness(${(1 + 0.04 * strength).toFixed(3)}) contrast(${(1 + 0.02 * strength).toFixed(3)}) hue-rotate(${(-4 * strength).toFixed(2)}deg)`
      );
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
  if (settings.outputSize) {
    return { width: settings.outputSize.width, height: settings.outputSize.height };
  }
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
  const rotated = rotation === 90 || rotation === 270;
  const tmpWidth = rotated ? Math.round(sh) : Math.round(sw);
  const tmpHeight = rotated ? Math.round(sw) : Math.round(sh);
  const { width, height } = outputSize(settings, naturalWidth, naturalHeight);

  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, width, height);

  // 先按旋转绘制到临时画布，再 cover 适配目标尺寸
  const tmp = document.createElement("canvas");
  tmp.width = tmpWidth;
  tmp.height = tmpHeight;
  const tctx = tmp.getContext("2d");
  if (tctx) {
    tctx.save();
    const filters = buildFilterChain(settings);
    if (filters.length > 0) tctx.filter = filters.join(" ");
    tctx.translate(tmpWidth / 2, tmpHeight / 2);
    tctx.rotate((rotation * Math.PI) / 180);
    tctx.drawImage(image, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
    tctx.restore();
  }
  const scale = Math.max(width / tmpWidth, height / tmpHeight);
  const drawWidth = tmpWidth * scale;
  const drawHeight = tmpHeight * scale;
  ctx.drawImage(tmp, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);

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
