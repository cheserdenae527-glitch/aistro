# D4 — 视觉设计补充项（task plan）

> 补充：PDF 导出 + 菜单多菜品分页 + 画布尺寸模板适配。

## 步骤

### 后端
- [x] menu_designs 增加 output_pages（JSONB）+ 迁移 f6d0a1b2c3d4
- [x] menu_render：render_menu_pages（XHS 6/页、A4 12/页）+ PDF 转换
- [x] render API 返回多页；新增 export-pdf
- [x] 测试：分页、PDF、409/400（design 30 passed）

### 前端
- [x] 画布尺寸模板（原始 / 小红书 / A4）+ renderToCanvas 适配
- [x] editStack 增加 output_size + 序列化/单测
- [x] 菜单预览多页 + 导出 PNG 多页 + 导出 PDF

### 验证
- [x] pytest + 前端 test/build + Playwright（D4 E2E 通过）
- [x] alembic upgrade + 契约文档更新