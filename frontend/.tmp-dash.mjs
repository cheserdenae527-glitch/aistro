
import { chromium } from "playwright";
const BASE = "http://localhost:8010";
const browser = await chromium.launch({ headless: true, args: ["--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required", "--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1000, height: 900 } });
await page.goto(`${BASE}/dashboard.html`, { waitUntil: "networkidle" });
console.log("title:", await page.title());
const btns = await page.locator("button").allTextContents();
console.log("buttons:", JSON.stringify(btns.map(b => b.trim()).filter(Boolean)));
console.log("has video:", await page.locator("video").count());
// 找开始连接按钮
const startBtn = page.locator('button:has-text("开始连接")').first();
if (await startBtn.count()) {
  await startBtn.click();
  console.log("clicked 开始连接");
} else {
  console.log("无开始连接按钮");
}
let ok = false;
for (let i = 0; i < 40; i++) {
  await page.waitForTimeout(1000);
  const st = await page.textContent("#status-text, #connection-status").catch(() => "");
  const hasVideo = await page.evaluate(() => { const v = document.getElementById("video"); return v ? { readyState: v.readyState, t: v.currentTime, w: v.videoWidth, h: v.videoHeight } : null; });
  if (hasVideo && hasVideo.readyState >= 2 && hasVideo.t > 0) { ok = true; console.log("video playing at", i, "s:", JSON.stringify(hasVideo)); break; }
  if (i === 20) console.log("status after 20s:", st, JSON.stringify(hasVideo));
}
if (ok) { await page.locator("#video").screenshot({ path: "D:/two/.planning/livestream/dash_check.png" }); }
await browser.close();
console.log(ok ? "OK dashboard 出画面" : "FAIL dashboard 无画面");
process.exit(ok ? 0 : 3);
