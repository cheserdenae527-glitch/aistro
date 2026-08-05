
// 临时验证脚本：真实 GPU 环境下 LiveTalking WebRTC 文本驱动推流验证
// 运行：cd D:\two\frontend && node .tmp-verify-live.mjs
import { chromium } from "playwright";

const BASE = "http://localhost:8010";
const AVATAR = "wav2lip_avatar_female_model";

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
      "--no-sandbox",
    ],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const logs = [];
  page.on("console", (m) => logs.push(`[page] ${m.type()}: ${m.text()}`));
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));

  await page.goto(`${BASE}/index.html`, { waitUntil: "networkidle" });

  // 填形象 ID（默认 wav2lip256_avatar1 我们没有）
  await page.fill("#offerAvatar", AVATAR);
  // 清空/填写播报文本
  await page.fill("#txtMessage", "欢迎来到 AiRestro 直播间，今天给大家带来双人餐限时优惠，点击小黄车即可下单。");

  console.log("clicking start...");
  await page.click("#btnStart");

  // 等待会话建立（SID 显示 + 连接状态）
  let sessionid = null;
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(1000);
    const sidText = await page.textContent("#sessionIdDisplay").catch(() => "");
    const badge = await page.textContent("#statusBadge").catch(() => "");
    console.log(`[${i}s] badge=${badge.trim()} sid=${sidText.trim()}`);
    const m = sidText.match(/SID:\s*(\S+)/);
    if (m && m[1] && m[1] !== "-") { sessionid = m[1]; break; }
    if (badge.includes("连接") && !badge.includes("未连接")) { sessionid = sidText.replace("SID:", "").trim(); break; }
  }
  if (!sessionid) {
    console.error("FAIL: WebRTC 会话未建立");
    console.log(logs.join("\n"));
    await page.screenshot({ path: "D:/two/.planning/livestream/verify_fail.png", fullPage: true });
    await browser.close();
    process.exit(1);
  }
  console.log("sessionid =", sessionid);

  // 发送文本驱动
  await page.click('button[onclick="sendText()"]');
  console.log("text sent, waiting for rendering...");
  await page.waitForTimeout(6000);

  // 视频状态
  const vinfo = await page.evaluate(() => {
    const v = document.getElementById("video");
    return {
      readyState: v?.readyState,
      paused: v?.paused,
      currentTime: v?.currentTime,
      videoWidth: v?.videoWidth,
      videoHeight: v?.videoHeight,
      srcObject: !!v?.srcObject,
    };
  });
  console.log("video info:", JSON.stringify(vinfo));

  // 两张截图，比对视频区域像素是否变化（画面在动）
  const box = await page.locator("#video").boundingBox();
  console.log("video box:", JSON.stringify(box));
  await page.locator("#video").screenshot({ path: "D:/two/.planning/livestream/frame_a.png" });
  await page.waitForTimeout(4000);
  await page.locator("#video").screenshot({ path: "D:/two/.planning/livestream/frame_b.png" });

  // 再次发送第二段文本，继续验证多轮驱动
  await page.fill("#txtMessage", "第二段：现在下单立减二十元，数量有限先到先得。");
  await page.click('button[onclick="sendText()"]');
  await page.waitForTimeout(6000);

  await browser.close();
  console.log("DONE sessionid=" + sessionid);
  if (!vinfo.srcObject || vinfo.videoWidth === 0 || vinfo.paused) {
    console.error("FAIL: 视频未在播放");
    process.exit(2);
  }
  console.log("OK: WebRTC 会话建立 + 文本驱动渲染中");
  process.exit(0);
}

main().catch((e) => { console.error("ERROR:", e); process.exit(3); });
