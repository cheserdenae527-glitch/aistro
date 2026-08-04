# D7 — S1 内容工坊后端（task plan）

## 步骤

### 1. 数据模型
- [x] studio_projects / studio_copies / studio_decks 模型 + __init__ 注册
- [x] design_asset_source 枚举加 studio

### 2. Alembic 迁移
- [x] b1d2e3f4a5b6_add_studio_tables

### 3. Schema
- [x] app/schemas/studio.py

### 4. AI Agents
- [x] copy agent（11 维度，5 标题+正文+标签+配图指导）
- [x] paginate agent（正文 → page_specs）

### 5. 渲染 + QA
- [x] Editorial / Swiss 模板 HTML + theme presets
- [x] Playwright 1080x1440 截图渲染服务
- [x] 4-band 密度 + 溢出 + 底部空白 QA

### 6. API
- [x] 项目 CRUD / copy generate / decks / deck 详情 / export-to-design
- [x] 鉴权 / 频控 / 敏感词 / 上传校验 / 素材所有权

### 7. 测试
- [x] test_studio.py 全绿（24 passed）

### 8. 契约文档
- [x] docs/contracts/studio-api.md
