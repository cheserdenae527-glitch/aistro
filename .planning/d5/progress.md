# D5 Progress

## 2026-08-04
- 开始 D5：编辑器交互补强。

## 2026-08-04 实现
- 撤销/重做：文字拖拽结束提交历史节点；Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y；工具栏显示步数。
- 提示词可重复：Redis 24h 缓存 + temperature 0.5；缓存命中跳过频控（真实接口二次调用返回相同提示词）。
- 后台生图：designJobs store 全局跟踪，离开页面不中断，完成弹通知；返回编辑器自动恢复候选；同 key 防重复提交。
- 验证：design 32 passed；前端 13 tests + build；Playwright 撤销/重做/快捷键通过，无控制台错误。
- D5 完成。

## 2026-08-04 用户反馈修正
- 一键美化：预设弹窗（轻度增强/鲜艳/柔和/色彩校正），参数可调。
- 撤销栈重构为 {settings, sourceUrl} 快照：一键美化、AI 候选换源都可撤销/重做。
- 文字：CanvasPreview 预览直接绘制文字；放置按钮 autoInsertSpace=false，点击画布可放置。
- 提示词：去掉 Redis 缓存，temperature 0.85 + 系统约束换表达；真实验证同参数两次结果不同。
- 验证：design 30 passed；前端 14 tests + build；Playwright 文字放置/美化撤销/快捷键通过。

## 2026-08-04 统一美化入口
- 移除工具栏“一键美化”与预设弹窗，统一为“AI 美化”。
- 预览卡片新增“前后对比”：AI 美化/候选换源后，左半屏显示美化前、右半屏显示当前结果。
- 移除 Pillow 结果对照区；后端 /beautify 保留兼容，契约已标注。
- 验证：前端 14 tests + build；Playwright 确认旧按钮消失、AI 美化存在、前后对比按钮就位。

## 2026-08-04 背景替换/菜品增强支持 AI 提示词
- 后端 generate_edit_prompt 支持 ai/bg/enhance，各类型独立系统提示词与侧重点。
- 接口 /ai-beautify/prompt 增加 kind 字段；契约已更新。
- 前端弹窗统一显示“侧重点 + AI 生成提示词”，bg 默认深夜暖光、enhance 默认突出光泽、ai 默认提升食欲感。
- 验证：design 30 passed；前端 14 tests + build；Playwright 确认两个弹窗均有 AI 生成提示词入口。

## 2026-08-04 滤镜扩展
- 新增 6 个滤镜：胶片、青橙、冷调、柔光、暗调、清新（原 5 个保留）。
- 新增“滤镜强度”滑杆（0-100），所有滤镜按强度缩放，原图/黑白也支持渐入。
- editStack 增加 filterStrength 字段并序列化；canvasRenderer 按强度计算滤镜链。
- 验证：前端 15 tests + build；Playwright 确认 6 个新滤镜与强度滑杆均可见，无控制台错误。