# D4 Findings

- Pillow 可把多张 PNG 存成单文件 PDF（save_all + append_images + resolution）。
- render_menu 现有 XHS 截断 6 个、A4 截断 12 个，改造为按页渲染最自然。
- 画布尺寸模板可在 EditorSettings 增加 output_size，renderToCanvas 按 cover 适配。