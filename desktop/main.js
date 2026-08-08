/* AiRestro 桌面端主进程：窗口 + 内置静态服务 + 后端自动拉起。 */
const { app, BrowserWindow, dialog } = require("electron");
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