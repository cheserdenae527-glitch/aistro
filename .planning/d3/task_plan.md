# D3 — 菜单设计前端 + 集成验证（task plan）

> 来源：docs/PLAN-DESIGN.md（D3）+ docs/SPEC-DESIGN.md v0.1 + docs/contracts/design-api.md
> 目标：模板选择、菜品勾选、渲染导出全链路可演示。

## 步骤
- [x] 编辑器加 Tabs：素材与编辑 / 菜单设计
- [x] MenuDesignPanel：
  - 模板选择 xhs_menu_01 / a4_menu_01
  - ItemPicker（只展示 dish + active，勾选/分区/排序/override）
  - 8 色板 + 自定义四色
  - 菜单 CRUD + version 409 处理
- [x] 渲染预览 + 导出下载（预签名 URL）
- [x] 契约一致性反查（15/15 覆盖）
- [x] 端到端验证：上传 → 建菜单 → 渲染 → 导出
- [x] 前端 test（7 passed）+ build + Playwright 全链路
