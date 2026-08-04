# D8 Progress

## 2026-08-04
- 开始 S2 内容工坊前端。

## 2026-08-04 实现
- 路由 /studio + /studio/:id，侧边栏「内容工坊」。
- studio.ts 服务层 + studio.ts utils（表单校验、QA 汇总、主题常量、toggleSelection/addWithCap）。
- StudioIndexPage：按商家/门店分组列表 + 新建弹窗。
- StudioEditorPage：三步流程（文案生成 429 倒计时 → 卡组模板/色板/页数/素材/渲染预览+QA 徽标 → 导出跳转 /design/:id）。
- AssetPickerDrawer：素材库引用 + 直接上传，总数 ≤8，上传类型/大小校验。
- 后端增强：multipart 卡组支持 asset_ids（素材库+上传可同时用），新增测试。
- 验证：Vitest 29 passed（新增 21）；lint/typecheck/build 全绿；真实 API 冒烟（4 页卡组 QA 全过、导出到设计素材 source=studio）；Playwright UI 冒烟全流程通过。

## 2026-08-04 修复：卡组生成网络错误
- 根因1：用户短时间内重复生成命中 60s 频控（后端正确返回 429），但 Vite 代理把 429 响应截断成 500/ERR_CONTENT_LENGTH_MISMATCH，反馈混乱。
- 根因2：前端 axios 默认 30s 超时 < 卡组渲染 10-30s+，客户端中断连接导致 content-length mismatch。
- 修复：前端 decks/copy 请求超时改为 180s/60s；429 检测更健壮（状态码或文案），显示倒计时；runGenerateDeck 防重入。
- 修复：后端捕获 openai.RateLimitError -> 429、APIError -> 502（不再裸 500）。
- 修复：vite.config.ts 代理目标固定 127.0.0.1:8000（避免 IPv6 歧义），移除调试钩子。
- 服务重启：start_services.py 的 npm run dev 偶发未拉起，改用 Start-Process node vite 直接启动并更新 PID。
- 验证：浏览器上下文 decks 全链路 200/rendered（11s）；28 backend + 29 frontend 测试全绿。

## 2026-08-04 增强：卡组素材支持 AI 生图
- 素材选择 Drawer 改为三段式：素材库 / 上传图片 / AI 生图。
- AI 生图：提示词默认预填 image_guide.cover_prompt（可编辑），配图指导 pages[] 的 prompt 以可点击标签填充；调用视觉设计 AI 生图接口（豆包）生成 4 张候选，点击选用，可多次生成。
- 后端：卡组 asset_ids 校验放宽为 active 或 pending（AI 候选），所有权/归属校验不变；新增测试。
- 新增 candidateToAsset 工具 + 测试；Drawer 增加已选素材预览/移除。
- 真实验证：AI 生图 4 张候选（93s）→ 卡组引用渲染成功（12s，4 页），source_assets 正确。
- 前端 typecheck/lint/build 全绿，Vitest 30 passed；后端 test_studio 28 passed。

## 2026-08-04 增强：配图提示词 AI 丰富
- 新增后端 POST /studio/copies/{copy_id}/image-prompt/enrich：先提炼配图指导核心想法，再结合门店信息扩写成完整生图提示词（主体/场景/光线/构图/氛围/色彩/质感/3:4 画幅），返回 {main_idea, prompt}。
- 新增 StudioImagePromptAgent（DeepSeek）+ 频控 20s + 敏感词 + openai 错误映射；5 个测试。
- 前端 AI 生图区：点配图指导标签自动「填充 + AI 丰富」，也可手动编辑后点「丰富提示词」；显示提炼出的核心想法。
- 真实验证：配图方向 -> enrich 200（5s），输出核心想法 + 覆盖环境/菜品/灯光/构图/氛围/色彩/质感的完整提示词。
- 后端 test_studio 34 passed、前端 Vitest 30 passed、lint/typecheck/build 全绿。

## 2026-08-04 增强：AI 生图显示进度
- 豆包生图流式接口支持 on_progress 回调（每张 partial_succeeded 递增上报）。
- 设计异步 job（generate/job）运行中把 progress/stage 写入 job.result（5% 提交 → 25/50/75/100% 逐张 → 95% 保存 → 100% 完成），成功后 result 仍为 {batch_id, candidates}。
- 前端素材 Drawer 的 AI 生图改用异步 job + 2s 轮询，展示 antd Progress 进度条 + 阶段文案（已生成 x/4 张）；失败/429/超时都有提示。
- 新增豆包进度回调单测；修复既有 fake_stream 签名。
- 真实验证：job 轮询观察到 5%→25%(1/4)→75%(3/4)→100%(4/4)→完成，89s 出 4 张候选。
- 后端 test_doubao 10 passed；前端 Vitest 30 passed、lint/typecheck/build 全绿。
- 全套验证：backend test_design 35 + test_studio 34 + test_doubao 10 全绿；前端 Vitest 30、lint/typecheck/build 全绿。

## 2026-08-04 增强：卡组预览放大 + 模板/色板样式
- 新增 DeckPreviewModal：点击预览图放大查看大图（1080x1440），左右翻页（按钮 + ←→ 方向键）、Esc 关闭、每页 QA 徽标（未通过页带问题 Popover）。
- 预览区新增「样式」信息条：模板（Editorial/Swiss）+ 色板名 + paper/accent/ink 三色色块；deckStyle 记录卡组实际使用的模板/色板（加载历史卡组与重新生成都正确）。
- 模板卡（Step2）改用当前选中色板的 paper/ink/accent 渲染，实时预览「模板 x 色板」组合效果。
- 共享 QaBadge 提取到 DeckPreviewModal.tsx（内联预览与放大弹窗复用）。
- UI 验证：样式标签/放大弹窗/←→翻页/Esc 关闭全部通过；Vitest 30、lint/typecheck/build 全绿。
