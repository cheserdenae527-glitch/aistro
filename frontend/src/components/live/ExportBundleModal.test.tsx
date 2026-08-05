// 导出开播包弹窗测试 — 下载引擎文件 / 下载开播包 JSON
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LiveExportBundle } from "../../services/live";
import ExportBundleModal from "./ExportBundleModal";

const bundle: LiveExportBundle = {
  script_markdown: "# 火锅直播间\n## 开场留人（60s）\n欢迎来到直播间\n",
  persona_json: {
    name: "店长小雅",
    personality: "亲切热情，懂美食",
    style: "烟火气",
    knowledge_scope: "本店菜品",
    forbidden_topics: ["政治", "宗教"],
  },
  wordlist: ["加微信", "regex:广告\\d+"],
  reply_rules: [{ trigger: "优惠", reply: "今日套餐 9.9 元起", mode: "manual" }],
  compliance: { pass: true, items: [{ key: "ai_label", ok: true, detail: "AI 标识文案非空" }] },
  engine_guide: "1. 启动 LiveTalking\n5. LiveTalking 水印提醒\n6. AI 标识文案提醒",
};

interface DownloadRecord {
  download: string;
  href: string;
}

function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

describe("ExportBundleModal · 下载", () => {
  let downloads: DownloadRecord[] = [];
  let blobs: Blob[] = [];
  const origCreateObjectURL = URL.createObjectURL;
  const origRevokeObjectURL = URL.revokeObjectURL;

  beforeEach(() => {
    downloads = [];
    blobs = [];
    URL.createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return "blob:mock";
    });
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      downloads.push({ download: this.download, href: this.href });
    });
  });

  afterEach(() => {
    URL.createObjectURL = origCreateObjectURL;
    URL.revokeObjectURL = origRevokeObjectURL;
    vi.restoreAllMocks();
  });

  function renderModal() {
    render(<ExportBundleModal open bundle={bundle} onClose={vi.fn()} />);
  }

  it("下载引擎文件：persona.json / wordlist.txt / script.md / reply_rules.json / engine_guide.txt", async () => {
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: /下载引擎文件/ }));

    const names = downloads.map((d) => d.download).sort();
    expect(names).toEqual([
      "engine_guide.txt",
      "persona.json",
      "reply_rules.json",
      "script.md",
      "wordlist.txt",
    ]);
    expect(downloads.every((d) => d.href === "blob:mock")).toBe(true);

    // persona.json 内容为引擎可读人设
    const personaText = await readBlobText(blobs[0]);
    expect(personaText).toContain('"name": "店长小雅"');
    // wordlist.txt 每行一词（含 regex: 前缀）
    const wordlistText = await readBlobText(blobs[1]);
    expect(wordlistText.split("\n")).toEqual(["加微信", "regex:广告\\d+"]);
  });

  it("下载开播包：单个 JSON 含全部六字段", async () => {
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: /下载开播包/ }));

    expect(downloads).toHaveLength(1);
    expect(downloads[0].download).toMatch(/^livestream-bundle-\d{4}-\d{2}-\d{2}\.json$/);
    const parsed = JSON.parse(await readBlobText(blobs[0])) as LiveExportBundle;
    expect(parsed.script_markdown).toBe(bundle.script_markdown);
    expect(parsed.persona_json.name).toBe("店长小雅");
    expect(parsed.wordlist).toEqual(["加微信", "regex:广告\\d+"]);
    expect(parsed.reply_rules).toHaveLength(1);
    expect(parsed.compliance.pass).toBe(true);
    expect(parsed.engine_guide).toContain("LiveTalking 水印提醒");
  });
});
