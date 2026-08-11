# AiRestro XHS Bridge（自建扩展 · 阶段 3 最小闭环）

学习 Beav 机制的自建 Chrome 扩展：真实登录会话内采集小红书笔记，直连本地 AiRestro 后端。

## 能力（阶段 3）
- 被动拦截：主世界 monkey-patch fetch/XHR，缓存页面自己请求的 API 响应（`window.__AISTRO_XHS_CAPTURE__`）
- 三源提取：`__INITIAL_STATE__`（SSR）→ 被动拦截的 `interact_info`（完整互动指标）→ DOM 兜底
- 保存当前笔记 → POST `http://127.0.0.1:8000/api/v1/bridge/notes`
- 采集评论 / 收集本页链接（批量入口，阶段 4 接入队列）

## 加载
1. Chrome → `chrome://extensions` → 开发者模式 → 加载已解压 → 选本目录
2. 登录小红书（必须已登录，真实会话）
3. 打开一篇笔记 → 点扩展图标 → 「保存当前笔记」
4. 后端未启动时弹窗会提示；先在 backend 启动 `python start_services.py`

## 后端桥接口
- `GET /api/v1/bridge/health`
- `POST /api/v1/bridge/notes`  `{ "note": {id, xsec_token, note_card, source_url, ...} }`
- `POST /api/v1/bridge/comments`  `{ "noteId": "...", "comments": [...] }`

## 设计要点（对照 Beav）
| 机制 | 本扩展实现 |
|---|---|
| 被动拦截 | `src/xhsBridge.js`（MAIN world） |
| 三源提取 | `src/content.js` |
| 滚动/验证页工具 | `src/captureRuntime.js` |
| 串行上报 + 随机间隔 | `src/background.js`（阶段 4 扩展为批量队列） |
| 互动指标 | 拦截 feed 响应读 `interact_info`（liked/collected/comment/shared 齐全） |
| 响应体通道 | postMessage 携带 `result` + background 从 MAIN world 兜底读取（对齐 Beav 机制） |
