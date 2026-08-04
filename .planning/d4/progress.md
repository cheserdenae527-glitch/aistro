# D4 Progress

## 2026-08-04
- 开始 D4 补充项。

## 2026-08-04 实现
- 后端：output_pages 字段+迁移、render 多页、export-pdf、_menu_response 预签名多页。
- 前端：画布尺寸模板 Select、renderToCanvas cover 适配、菜单多页预览、分页 PNG 导出、PDF 导出。
- 验证：design 30 passed；前端 13 tests + build；Playwright 7 菜品 → 2 页渲染 + PDF 导出无报错。
- 注：全量套件中 test_reputation 有 4 个偶发失败（asyncio.run 与跨模块连接池串用），与 D4 无关；已加模块级清理 fixture 降低概率。
- D4 完成。