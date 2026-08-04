# 内容工坊模块 — 实现计划

> 基于 SPEC-CONTENT-STUDIO v0.1 · 独立于主项目里程碑

## 依赖与复用

| 能力 | 来源 | 状态 |
|---|---|---|
| DeepSeek LLM | `app.ai` 客户端模式 | 已有 |
| MinIO | `app.services.storage` | 已有 |
| 设计素材库 | `design_assets` / `design_projects` | 已有 |
| 敏感词 / 频控 | `app.core` | 已有 |
| Guizang 模板/校验 | `skills/guizang-social-card-skill/` | 已拷贝 |
| Viral Writer 方法论 | `skills/viral-writer-skill/SKILL.md` | 已拷贝 |
| Playwright | 需安装 | 新依赖 |

---

## S1 — 后端：模型 + API + 文案生成 + 卡组渲染

**目标**：文案生成、卡组渲染、QA、导出全部 API 可用。

### 任务清单

1. 安装依赖：`playwright`（Python）+ Chromium
2. Alembic 迁移：studio_projects / studio_copies / studio_decks
3. SQLAlchemy 模型 + Pydantic Schema
4. API：
   - 项目 CRUD
   - POST copy/generate（DeepSeek，11 维度 prompt，5 标题+正文+标签+配图指导）
   - POST decks（分页 LLM + 渲染 + QA + MinIO）
   - GET deck 详情
   - POST export-to-design（写入 design_assets）
5. 文案 Agent：Viral Writer 风格 prompt（小红书规范 + 11 维度）
6. 分页 Agent：正文 → page_specs（page_count 4-8）
7. 渲染服务：
   - 读取 Editorial / Swiss 模板 HTML
   - 参数化填充（标题/要点/图/色板 CSS 变量）
   - Playwright viewport 1080×1440 → screenshot PNG
   - 图片上传 MinIO
8. QA 服务：
   - PIL 4-band 密度检查
   - Playwright evaluate 溢出/底部空白
   - qa_report 写入 deck
9. 素材来源：asset_ids 引用（所有权/active 校验）+ multipart 上传
10. 鉴权 / 频控 / 敏感词 / 上传校验
11. 测试：
    - 文案生成：5 标题、正文长度、标签数量、敏感词 422
    - 分页：page_count 4-8 校验、越界 400
    - 渲染：输出 1080×1440 PNG、文件数量 = 页数
    - QA：密度检查通过/失败逻辑
    - 素材：asset_ids 跨门店 404、上传类型/大小校验
    - 导出：design_assets 创建成功、所有权校验
    - 鉴权 401 / 跨用户 404
12. 契约文档：`docs/contracts/studio-api.md`

### 交付物
- Swagger 可调用全部 API
- 后端可渲染一套完整小红书卡组
- pytest 全绿 + 契约文档

---

## S2 — 前端内容工坊

**目标**：项目 → 文案 → 卡组 → 导出全流程可用。

```
前置：S1
```

### 任务清单

1. 路由 `/studio` + `/studio/:id`，侧边栏入口
2. 项目列表页 + 新建（选门店）
3. Step 1 文案：
   - 表单 + 生成按钮（429 倒计时）
   - 5 标题卡片选择 + 正文可编辑 + 标签展示
   - 保存 copy
4. Step 2 卡组：
   - 模板卡片（Editorial/Swiss 视觉缩略）
   - 色板选择
   - 页数 4-8
   - 素材 Drawer（design_assets）+ 直接上传
   - 生成 → loading → 卡组横滑预览 + QA 标记
5. Step 3 导出：导出到视觉设计 → 跳转 /design/:id
6. 真实 API 联调（非 mock）：Swagger 反查契约文档一致性，不一致回写
7. 单元测试（Vitest）：表单校验、页数限制、素材选择状态

### 交付物
- 文案 → 卡组 → 导出全流程可操作
- 429/422/QA 失败提示

---

## S3 — 集成验证

**目标**：真实素材端到端跑通，视觉质量达标。

```
前置：S1 + S2
```

### 任务清单

1. 用视觉设计素材库真实菜品图生成卡组
2. 验证 Editorial + Swiss 各一套
3. QA 报告人工复核（密度/溢出）
4. 导出到视觉设计编辑器 → 继续编辑 → 保存
5. 契约一致性反查 + 文档回写
6. 与装修模块色板对比，视觉一致性检查

### 交付物
- 完整流水线可演示
- 卡组视觉质量通过 QA + 人工检查

---

## 执行顺序

```
S1 (后端+渲染) → S2 (前端) → S3 (集成验证)
```

每阶段独立对话，S2/S3 引用 `docs/contracts/studio-api.md`。

## 已知妥协

- Playwright 需要安装 Chromium（约 150MB），首次启动下载
- 渲染为同步执行，4-8 页约 10-30 秒，MVP 接受；后续可切任务队列
- 卡组 QA 是自动化初筛，审美终审仍需人工
- 模板资产来自 Guizang skill，商用前需授权（见 SPEC 许可提示）
