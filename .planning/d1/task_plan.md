# D1 — 视觉设计板块后端（task plan）

> 来源：docs/PLAN-DESIGN.md（D1）+ docs/SPEC-DESIGN.md v0.1
> 目标：设计项目/素材/菜单 API 可用，一键美化与菜单渲染可调用，pytest 全绿 + 契约文档。

## 阶段

### 1. 基础设施
- [x] 检查/补齐依赖（Pillow 已在 requirements）
- [x] 下载 Noto Sans SC Regular + Bold 到 backend/assets/fonts/
- [x] 准备测试实拍图 fixture（warm restaurant photo）

### 2. 数据模型 + 迁移
- [x] SQLAlchemy：design_projects / design_assets / menu_designs
- [x] Alembic 迁移（derived_from_asset_id ON DELETE SET NULL）
- [x] app/models/__init__.py + alembic/env.py 注册

### 3. Schema + API
- [x] Pydantic schemas（project/asset/menu/generate/confirm/save/render）
- [x] design router：project CRUD
- [x] asset upload/update/delete（删除引用 409）
- [x] assets/generate（4 候选 pending + batch_id）
- [x] confirm（batch 同批处理、幂等 409）
- [x] beautify / bg-replace / enhance / save（派生折叠）
- [x] menu CRUD + render（version 乐观锁、items 校验）
- [x] 鉴权 / 频控(user+shop) / 敏感词 / base64 大小

### 4. 服务层
- [x] auto_beautify（暖调保留，白平衡可选）
- [x] generate_edited（豆包通用编辑入口）
- [x] menu render 纯函数 + xhs/a4 模板 + 中文字体

### 5. 测试
- [x] 一键美化（暖调保留）
- [x] 菜单渲染（尺寸/中文）
- [x] 鉴权 401 / 跨用户 404
- [x] 敏感词 422 / 频控 429（mock 豆包）
- [x] 候选生命周期 / batch 隔离 / 幂等 409
- [x] 派生折叠 / GET 排除派生 / 删除引用 409
- [x] render version 409 / override 优先 / items 400

### 6. 契约文档
- [x] docs/contracts/design-api.md

### 7. 验证
- [x] pytest 全绿（41 passed）
- [x] Alembic upgrade head 到 e5f0d1a2b3c4
- [x] Swagger 路由可访问（localhost:8000/openapi.json 含 13 条 design 路径）
