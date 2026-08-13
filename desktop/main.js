/* AiRestro 桌面端主进程：窗口 + 内置静态服务 + 后端自动拉起。 */
const { app, BrowserWindow, dialog, ipcMain, session } = require("electron");
const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const BACKEND_URL = "http://127.0.0.1:8000";
const STATIC_PORT = 5174;
const FRONTEND_DIST = path.join(__dirname, "..", "frontend", "dist");

let mainWindow = null;
let backendProc = null;
let backendSpawned = false;
let staticServer = null;

function fetchPing(timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/ping`, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackend() {
  if (await fetchPing()) return true;
  backendProc = spawn(
    process.env.PYTHON || "python",
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    {
      cwd: path.join(__dirname, "..", "backend"),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    }
  );
  backendSpawned = true;
  backendProc.stdout.on("data", (d) => process.stdout.write(d));
  backendProc.stderr.on("data", (d) => process.stderr.write(d));
  for (let i = 0; i < 30; i += 1) {
    await new Promise((r) => setTimeout(r, 1000));
    if (await fetchPing()) return true;
  }
  return false;
}

function startStaticServer() {
  const types = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
  };

  const server = http.createServer((req, res) => {
    // API 请求转发到后端
    if (req.url.startsWith("/api/")) {
      const proxy = http.request(
        {
          host: "127.0.0.1",
          port: 8000,
          path: req.url,
          method: req.method,
          headers: { ...req.headers, host: "127.0.0.1:8000" },
        },
        (pRes) => {
          res.writeHead(pRes.statusCode, pRes.headers);
          pRes.pipe(res);
        }
      );
      proxy.on("error", () => {
        res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("后端服务不可用");
      });
      req.pipe(proxy);
      return;
    }

    // 静态文件（SPA history 回退到 index.html）
    const pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    const requested = pathname === "/" ? "/index.html" : pathname;
    const file = path.resolve(path.join(FRONTEND_DIST, requested));
    if (!file.startsWith(path.resolve(FRONTEND_DIST))) {
      res.writeHead(403);
      res.end();
      return;
    }
    fs.readFile(file, (err, data) => {
      if (err) {
        // 前端路由回退
        fs.readFile(path.join(FRONTEND_DIST, "index.html"), (err2, html) => {
          if (err2) {
            res.writeHead(404);
            res.end("not found");
            return;
          }
          res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
          res.end(html);
        });
        return;
      }
      res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
      res.end(data);
    });
  });

  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(STATIC_PORT, "127.0.0.1", () => resolve(server));
  });
}

// ---- 小红书 Cookie 扫码登录（阶段A）：弹出登录窗口 → 真实验证 → 写入 Cookie 池 ----
async function apiPost(path, token, body) {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (res.status === 401 || res.status === 403) return { httpStatus: res.status };
  return { httpStatus: res.status, body: await res.json().catch(() => null) };
}

function xhsLogin(token) {
  return new Promise((resolve) => {
    const LOGIN_PARTITION = "persist:xhs-login";
    const ses = session.fromPartition(LOGIN_PARTITION);
    ses.clearStorageData().catch(() => {});
    let win = new BrowserWindow({
      width: 480,
      height: 720,
      title: "小红书登录 - 扫码后自动抓取 Cookie",
      autoHideMenuBar: true,
      webPreferences: { session: ses, contextIsolation: true, nodeIntegration: false },
    });
    let settled = false;
    let verifying = false;
    let seenCount = 0;
    let verifyFailCount = 0;
    let pollTimer = null;
    let timeoutTimer = null;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (pollTimer) clearInterval(pollTimer);
      if (timeoutTimer) clearTimeout(timeoutTimer);
      try { if (!win.isDestroyed()) win.close(); } catch {}
      resolve(result);
    };
    win.on("closed", () => finish({ ok: false, action: "cancel" }));
    timeoutTimer = setTimeout(() => finish({ ok: false, action: "timeout" }), 10 * 60 * 1000);

    pollTimer = setInterval(async () => {
      if (verifying) return;
      try {
        const cookies = await ses.cookies.get({ domain: ".xiaohongshu.com" });
        if (!cookies.find((c) => c.name === "web_session" && c.value)) {
          seenCount = 0;
          verifyFailCount = 0;
          return;
        }
        seenCount += 1;
        // 小红书扫码后有约 3 秒「确认登录」界面，期间 web_session 可能已提前下发；
        // 必须连续 2 轮（约 4 秒）稳定存在后才验证录入，避免在正式登录前就写入 Cookie。
        if (seenCount < 2) return;
        const cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
        verifying = true;
        verifyFailCount += 1;
        // 延迟 500ms 再验证：防页面跳转/cookie 未写稳的时序竞态
        setTimeout(async () => {
          try {
            const v = await apiPost("/crawler/pool/cookies/verify", token, { cookie: cookieStr });
            if (v.httpStatus === 401 || v.httpStatus === 403) {
              finish({ ok: false, action: "token_expired", error: "登录态已过期，请重新登录系统" });
              return;
            }
            if (!v.body || v.body.ok !== true) {
              if (v.body && v.body.reason === "network_error") {
                finish({ ok: false, action: "verify_failed", reason: "network_error", error: v.body.error || "" });
              } else if (verifyFailCount >= 3) {
                // 登录态确实不完整（可能扫错/游客态），提示重扫
                finish({ ok: false, action: "verify_failed", reason: "auth_incomplete", error: (v.body && v.body.error) || "" });
              }
              return;
            }
            const add = await apiPost("/crawler/pool/cookies", token, { cookie: cookieStr, label: "" });
            if (add.httpStatus === 401 || add.httpStatus === 403) {
              finish({ ok: false, action: "token_expired", error: "登录态已过期，请重新登录系统" });
              return;
            }
            if (add.body && (add.body.action === "added" || add.body.action === "replaced")) {
              finish({
                ok: true,
                action: add.body.action,
                cookieId: add.body.id,
                evicted: add.body.evicted ? add.body.evicted.id : null,
                account_id: v.body.account_id || "",
              });
            } else {
              finish({ ok: false, action: "pool_full", error: (add.body && add.body.detail) || "Cookie 池已满" });
            }
          } catch (e) {
            finish({ ok: false, action: "network_error", error: String((e && e.message) || e) });
          } finally {
            verifying = false;
          }
        }, 500);
      } catch { /* 轮询异常忽略，继续下一轮 */ }
    }, 2000);

    win.loadURL("https://www.xiaohongshu.com").catch(() => {
      finish({ ok: false, action: "network_error", error: "无法打开小红书登录页" });
    });
  });
}

ipcMain.handle("xhs:login", async (_event, token) => {
  if (!token) return { ok: false, action: "token_expired", error: "缺少登录态" };
  try {
    return await xhsLogin(token);
  } catch (e) {
    return { ok: false, action: "network_error", error: String((e && e.message) || e) };
  }
});

async function createWindow() {
  const backendOk = await ensureBackend();
  if (!backendOk) {
    dialog.showErrorBox(
      "启动失败",
      "后端服务未能启动。请确认：\n\n1. 本机 PostgreSQL 正在运行（服务 postgresql-x64-17）\n2. Python 环境正常\n\n然后重新打开应用。"
    );
    app.quit();
    return;
  }

  let url = process.env.VITE_URL;
  if (!url) {
    staticServer = await startStaticServer();
    url = `http://127.0.0.1:${STATIC_PORT}/`;
  }

  mainWindow = new BrowserWindow({
    width: 1500,
    height: 950,
    minWidth: 1100,
    minHeight: 720,
    title: "AiRestro 工作台",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.loadURL(url);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on("window-all-closed", () => {
    if (backendSpawned && backendProc) {
      backendProc.kill();
    }
    if (staticServer) {
      staticServer.close();
    }
    app.quit();
  });
}