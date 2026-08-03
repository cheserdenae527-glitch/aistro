# D2 Findings

## 现有前端模式
- React 18 + TS + AntD 5 + axios + zustand；Vite proxy `/api -> localhost:8000`。
- 路由集中 App.tsx；侧边栏 horizontal Menu。
- 装修模块 CropModal 内嵌在 ProfileEditorPage，可抽取复用。
- 测试：Vitest + @testing-library（jsdom），已有 NoteCard.test.tsx。

## 联调发现
- MinIO 已配置 CORS（Access-Control-Allow-Origin: http://localhost:3000），画布导出可用。
- AntD 5.22 Slider 没有 onBeforeChange 类型；历史起点改为首次 onChange 记录。
- Playwright Chromium 已安装，可直接做无头冒烟。
