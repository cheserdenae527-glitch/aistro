# D2-AI — AI 一键美化（task plan）

> 在 D2 编辑器内新增 AI 美化入口：Pillow 美化之外，用豆包对原图做高级美食摄影增强。

## 步骤
- [x] 后端 schema：AiBeautifyRequest（prompt 可选 + 敏感词）
- [x] 后端路由 POST /assets/{aid}/ai-beautify（60s 频控、派生候选）
- [x] 后端测试：候选生命周期 + 敏感词 + 频控
- [x] 前端 designService.aiBeautify
- [x] 前端编辑器按钮 + 弹窗 + 候选确认
- [x] 契约文档更新
- [x] pytest（22 passed）+ 前端 build/test + Playwright 冒烟

## 增强：AI 生成美化提示词（按侧重点）
- [x] 后端 design_prompt 模块（DeepSeek 生成提示词）
- [x] POST /assets/{aid}/ai-beautify/prompt（focus/dish_name 可选、敏感词、20s 频控）
- [x] 前端弹窗：侧重点 Select + “AI 生成提示词”按钮 + 可编辑 textarea
- [x] 测试：25 passed + 前端 build/test + Playwright 冒烟
