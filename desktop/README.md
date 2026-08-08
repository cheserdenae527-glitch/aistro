# AiRestro 桌面端

把现有工作台包成 Electron 桌面窗口，脱离浏览器运行。

## 首次准备

1. 先构建前端静态文件（在项目根目录执行）：
   `cd frontend && npm install && npm run build`
2. 安装桌面端依赖（本目录）：
   `npm install`

## 运行

在 `desktop` 目录执行：

`npm start`

应用会自动：

- 检查后端 `127.0.0.1:8000`，没启动则自动拉起 FastAPI 后端
- 用内置静态服务加载 `frontend/dist`，并把 `/api` 转发到后端
- 打开桌面窗口（无需浏览器）

前置要求：本机 PostgreSQL 正在运行（服务 `postgresql-x64-17`）。

## 打包 Windows 安装包

`npm run dist`

产物在 `desktop/release/` 下（NSIS 安装程序）。

## 说明

- 如果想让桌面端连接已有的前端 dev server（而不是静态构建），可设置环境变量后启动：
  `VITE_URL=http://localhost:3000 npm start`
- 关闭窗口会退出应用；若后端是本应用拉起的，会一并停止；已运行中的后端不受影响。