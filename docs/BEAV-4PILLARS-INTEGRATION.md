# Beav 四方向架构 → AiRestro 落地蓝图

> 目标：把 Beav（RedBox）"浏览器内采集 + AI 遥控 + 本地知识库" 的四层机制，学过来并集成到 AiRestro 的爬虫板块，在尽量不触发小红书风控的前提下最大化数据采集成功率。
> 配套代码：`extensions/xhs-bridge/`（Chrome 扩展）、`backend/app/api/v1/browser_bridge.py`（FastAPI 桥）、`tools/browser_control/`（CDP 浏览器控制最小实现）。

---

## 0. 现状 vs 目标

| 维度 | AiRestro 现状（纯请求路线） | Beav 路线（真实浏览器会话） | 目标 |
|---|---|---|---|
| 请求签名 | RedCrack 纯 Python 逆向 x-s / x-rap-param | 直接调用页面自带的 `window.mnsv2`/`window.md5` 现场签名 | 两者并存：逆向失败时走浏览器桥 |
| 会话 | Cookie 字符串（易失效，需 F12 手动复制） | 真实登录浏览器，cookie/指纹永远是真的 | 浏览器桥兜底，Cookie 失效不再致命 |
| 已知痛点 | `user_posted data:null`、`x-rap-param 间歇失败`、频繁换 Cookie | 页面自己请求从不失败 | 浏览器被动采集直接绕过这些痛点 |
| 数据源 | 仅 API | API + `__INITIAL_STATE__` + DOM + 被动拦截 | 四源并用，取数最大化 |
| 风控 | 节流 + 熔断（`gate.py`） | 随机间隔 + 断点 + 验证页交接 + 单账号串行 | 保留现有 gate，扩展加入 Beav 策略 |

核心结论：**不要替换 RedCrack，而是把"浏览器桥"作为第二条腿**。两条腿共享同一套 `processor.py` 归一化和 `note_details` 存储，采集任务可以按需路由。

---

## 1. 方向一：采集机制（被动拦截 + SSR + DOM）

### Beav 的做法（参考实现）
1. **被动 API 拦截**：`xhsBridge.js` 在页面主世界 monkey-patch `window.fetch` / `XMLHttpRequest`，把小红书接口的 JSON 响应缓存进 `window.__REDBOX_XHS_RESPONSES__`（上限 120 条），并 postMessage 通知扩展——**页面自己发出的合法请求，零额外请求白嫖数据**。
2. **SSR 数据**：直接解析 `window.__INITIAL_STATE__`（`note.noteDetailMap`、`user.userPageData`），零请求。
3. **DOM 兜底**：选择器解析标题/正文/图片/视频/作者。
4. **主动请求（最后手段）**：`POST edith.xiaohongshu.com/api/sns/web/v1/feed`，`x-s` 由页面内 `window.mnsv2` 现场生成，请求体必须带 URL 里的 `xsec_token`。

### AiRestro 落地（本次交付 `extensions/xhs-bridge/`）
- `src/xhsBridge.js`：主世界拦截，同款实现（含 `__XHS_BRIDGE_CAPTURE__` 缓存 + `postMessage`）。
- `src/content.js`：`extract-note` 消息处理器，**把 DOM/SSR/拦截结果映射成 XHS API 的 `note_card` 形状**（`id/xsec_token/user/display_title/desc/image_list/video/interact_info/type/time`），这样 `processor.normalize_note()` **一行不用改**。
- `src/captureRuntime.js`：滚动/可见节点/验证页检测/随机间隔工具（从 Beav 提炼）。
- 主动 `feed` 调用：复用页面 `window.mnsv2` + `window.md5` 生成 `x-s`，同 Beav（`content.js` 内 `seccoreSign`）。

**收益**：`user_posted`/详情/搜索在真实会话里永远不会因为签名错误失败；Cookie 失效问题消失（登录态在浏览器里）。

---

## 2. 方向二：评论与批量（队列 + 限速 + 断点 + 去重）

### Beav 的做法
- 后台**串行任务队列**（一次只跑一个采集任务，可暂停/继续）。
- **随机间隔**：每条之间 `random(min,max)`，默认 1.5–3.5s，可配 3–6s，钳制 0.5–60s。
- **断点续采**：`redboxCaptureCheckpoints` 记录每条的状态机 `started → loaded → persisted/failed`。
- **去重跳过**：已采集 noteId 集合，下次自动跳过。
- **验证页检测**：命中 `人机验证/人类验证/安全验证/just a moment...` 即停并记录 `challenge`。
- 评论采集：滚动评论区（目标 200 条、最多 28 轮、连续 5 轮无新增即停）+ 点"展开/全部回复"。

### AiRestro 落地
- `background.js` 实现同款：串行队列、`sleepXhsCollectInterval`、`chrome.storage.local` 存 checkpoint 与已采集集合、挑战页检测。
- 评论：`content.js` 的 `extract-comments` 复用 `captureRuntime` 滚动逻辑。
- 批量：`collect-links`（当前页可见笔记链接）+ `search-keyword`（打开搜索页 → 滚动 → 收集链接）+ 逐个开隐藏标签页采集详情（`chrome.tabs.create({active:false})` → 等待 → 提取 → 关闭），**每条之间随机间隔**。
- 与现有 `services/crawler/tasks.py` 的关系：浏览器桥任务是**独立通道**，先落库 `note_details`，再由现有分析任务消费；不在内存任务表里重复造轮子。

---

## 3. 方向三：AI 浏览器控制（DOM 快照 + 节点点击 + MCP）

### Beav 的做法
- MCP 工具面（~90 个）：`tabs.list/create/claim`、`page.domSnapshot`、`page.click/type/select`、`node.click`、`page.waitForSelector`、`input.mouse*`、`cdp.send`…
- `domReader.js`：克隆 DOM → 清洗（删 script/隐藏节点）→ 属性白名单 → URL 绝对化 → 主列表容器打分。
- 节点 id 机制：`WeakMap` 分配自增 id，`node.click` 按 id 定位（校验 `isConnected`）。
- 安全护栏：`DANGEROUS_ACTION_TEXT`（保存/提交/发布/删除/退款…）拦截 + CDP 高危方法黑名单 + 审批分级。
- 站点调研宏：`research.run`（只读，`page_click` 模式打开详情，验证码/登录人工交接）。

### AiRestro 落地（本次交付 `tools/browser_control/cdp_client.py`）
- 用 **CDP（Chrome DevTools Protocol）** 连真实 Chrome（`--remote-debugging-port=9222`），提供：
  - `dom_snapshot()`（清洗后的可读 HTML，给 LLM 看）
  - `click(selector)` / `type(selector, text)`（滚动到视野 + 真实事件序列）
  - `inspect_point(x,y)`（`elementsFromPoint`）
  - `page_assets()`（图片/视频清单）
- 只读原则 + 危险动作正则（照搬 Beav 的思路）。
- **调研宏**：文档给出 `research.run` 状态机设计（搜索→筛选→收集→page_click 打开→抽取→关闭恢复→媒体下载），落地时复用扩展的提取器。
- 与 FastAPI 的关系：作为独立工具模块，供 AI Agent（后续接 OpenClaw/Codex/自研）调用；长期可挂 MCP server。

---

## 4. 方向四：桌面知识库与调研调度

### Beav 的做法
- **本地优先存储**：`knowledge/redbook/<noteId>/meta.json + 图片`、SQLite（`archive_samples` + 向量）。
- **索引管线**：MD5 去重 → 500 字符切片（50 重叠）→ embedding（OpenAI 兼容 `text-embedding-3-small`）→ 写向量表 → 版本号失效缓存。
- **混合检索**："向量优先 + grep 兜底"，RRF 融合，拼成带引用的 prompt context。
- **ACP Gateway**：本地 HTTP 网关，外部 Agent（Codex/OpenClaw）复用它会话/素材/任务。
- **Research Runner**：编排 `research.run` 宏（导航/登录交接/有界滚动/断点/产物持久化/知识入库/清理标签页）。

### AiRestro 落地
- 你已经有 `note_details`（JSONB 快照缓存）→ 这就是知识库底表；再加：
  - `bridge_inbox`（浏览器桥原始收件，可重放）
  - 检索端点 `GET /api/v1/bridge/knowledge/search?q=&top_k=`：先用 `ILIKE` 关键词 + 可选向量（Postgres `pgvector` 或外部 embedding API），拼带引用 context。
- 调度：现有 APScheduler（订阅刷新）+ 内存任务队列 → 后续接 Celery Beat；浏览器桥任务由扩展队列驱动，不占用后端调度。

---

## 5. 风控总策略（两腿共用）

```
浏览器桥（真实会话）                   纯请求（RedCrack）
├─ 被动拦截：零额外请求风险最低          ├─ gate.py：全局节流 + 熔断
├─ 主动请求：页面内签名 + 随机间隔        ├─ 随机延时 + 指数退避 + 代理池
├─ 验证页：识别即停 → 人工交接           └─ Cookie 健康检测
└─ 断点续采：中断不重锤
```

红线（沿用你项目 README 的立场）：
- 单账号串行，禁止并发轰炸；间隔钳制下限 0.5s 起，建议 ≥2s。
- 只抓公开笔记/评论/博主公开主页数据；不碰私信、手机号等个人信息。
- 验证码/滑块出现即停，交给人，不硬闯。
- 商业化落地前自行评估平台 ToS 与《反不正当竞争法》《个保法》风险。

---

## 6. 交付文件清单

| 文件 | 说明 |
|---|---|
| `extensions/xhs-bridge/manifest.json` | MV3 扩展清单（MAIN world 注入 xhsBridge） |
| `extensions/xhs-bridge/src/xhsBridge.js` | 被动拦截（fetch/XHR） |
| `extensions/xhs-bridge/src/captureRuntime.js` | 滚动/可见/验证页/间隔工具 |
| `extensions/xhs-bridge/src/content.js` | 提取器（INITIAL_STATE+DOM+拦截→note_card）+ 评论 + 签名 |
| `extensions/xhs-bridge/src/background.js` | 串行队列 + 批量 + 断点 + 上报 |
| `extensions/xhs-bridge/src/popup.*` | 采集控制台 UI |
| `backend/app/api/v1/browser_bridge.py` | FastAPI 桥（notes/comments/batch/health） |
| `tools/browser_control/cdp_client.py` | AI 浏览器控制最小实现（方向三） |
| `docs/BEAV-4PILLARS-INTEGRATION.md` | 本文档 |

## 7. 接入步骤

1. 后端：`app/api/v1/__init__.py` 注册 `browser_bridge_router`；重启 `python start_services.py`。
2. 扩展：Chrome → `chrome://extensions` → 开发者模式 → 加载已解压 → 选 `extensions/xhs-bridge`。
3. 登录小红书（重要：必须已登录，扩展用的是真实会话）。
4. 打开一篇笔记 → 点扩展图标 → "保存当前笔记"；或填关键词点"关键词采集"。
5. 数据进入 `POST /api/v1/bridge/notes` → `processor.normalize_note` → `note_details`。
