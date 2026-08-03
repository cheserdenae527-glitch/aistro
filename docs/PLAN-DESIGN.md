# 视觉设计板块 — 实现计划

> 基于 SPEC-DESIGN v0.1 · 独立于主项目里程碑

## 依赖与复用

| 能力 | 来源 |
|---|---|
| JWT + shop 所有权 | 装修模块 `_verify_shop_owner` |
| MinIO 上传/预签名 URL | `app.services.storage` |
| 豆包生图（参考图/4 张候选） | `app.ai.doubao_image` |
| 敏感词过滤 / 频控 | `app.core.sensitive_filter` / `rate_limit` |
| 8 色板预设 | `app.services.color_presets` |
| 前端 Canvas 裁剪 | 装修模块 CropModal（可抽取复用） |

---

## D1 — 后端数据模型 + API + 美化/渲染服务

**目标**：设计项目/素材/菜单全部 API 可用，一键美化与菜单渲染可调用。

### 任务清单

1. Alembic 迁移：design_projects / design_assets / menu_designs
   - design_assets 含 status(pending/active/discarded)、batch_id、derived_from_asset_id
   - derived_from_asset_id 外键 ON DELETE SET NULL
2. SQLAlchemy 模型 + Pydantic Schema
3. API：项目 CRUD、素材上传/更新/删除、菜单 CRUD（version 乐观锁）
   - DELETE asset 前检查菜单引用，被引用返回 409
   - render 带 version 乐观锁
4. **纯文生图 API**：POST /assets/generate（不依赖已有 asset），4 张候选落库 pending（batch_id 同批共享）后返回
5. **候选确认 API**：POST /assets/{aid}/confirm，按 batch_id 查询同批，选中 active、其余 discarded
   - bg-replace/enhance 候选带 derived_from_asset_id=原 aid
   - /save 时折叠：同项目 status=active 且 derived_from_asset_id=当前 aid 的候选置为 discarded
6. `auto_beautify`：Pillow 一键美化管线（默认保留暖调，白平衡可选，参数先用草案值再实拍图调参）
7. `generate_edited`：豆包通用编辑入口（纯文生图 / 背景替换 / 菜品增强，带参考图）
8. 菜单渲染服务：xhs_menu_01 + a4_menu_01 模板
   - 渲染服务为纯函数（配置 + 素材字节 → PNG 字节），为异步队列预留
   - **字体文件入库**：下载 Noto Sans SC（Regular + Bold）到 `backend/assets/fonts/`，本地/Docker 同一份
   - items 从 design_assets 实时取值，渲染时 join
9. 鉴权 / 频控（user+shop 维度）/ 敏感词 / base64 大小校验
10. 测试：
    - 一键美化：输出图片存在、尺寸/格式正确；**用真实餐厅实拍图验证暖调保留**
    - 菜单渲染：xhs/a4 输出尺寸正确、含中文字体文本
    - 鉴权 401 / 跨用户 404
    - 敏感词 prompt 422、频控 429（mock 豆包）
    - 候选生命周期：generate 返回 4 条 pending，confirm 后 1 active + 3 discarded
    - confirm 按 batch_id 同批处理（不误伤其他批次 active 素材）
    - confirm 幂等：非 pending 记录重复 confirm → 409
    - 派生折叠：bg-replace confirm 后 /save，派生候选 discarded、原 aid 保存成品
    - GET /assets 默认排除 derived_from_asset_id 非空记录
    - assets/generate 频控 60s
    - 素材删除被菜单引用 → 409
    - render version 不匹配 → 409
    - 渲染取值：override_* 优先于素材库字段
    - menu items asset_id 不属于当前 project → 400
    - menu items asset_id 非 active（discarded）→ 400
11. 契约文档：`docs/contracts/design-api.md`

### 交付物
- Swagger 可调用全部 API
- 后端可渲染小红书长图 + A4 菜单
- pytest 全绿 + 契约文档

---

## D2 — 前端实时图片编辑器

**目标**：上传/AI 生成图进入统一编辑器，所有操作实时预览。

```
前置：D1
```

### 任务清单

1. 路由 `/design` + `/design/:id`，侧边栏入口
2. 项目列表页 + 新建项目
3. 素材库面板（上传 / AI 生成 Drawer / 素材列表 / 删除）
   - AI 生成 Drawer：纯文生图 + 参考图 → POST /assets/generate → 4 候选 → confirm
   - 删除被引用素材：展示 409 拦截提示
4. CanvasPreview 实时预览组件
5. Toolbar + PropertyPanel：
   - 裁剪（复用 CropModal）/ 旋转
   - 亮度 / 对比度 / 饱和度 / 色温滑块（实时重绘）
   - 滤镜（暖食 / 日系 / 高饱和 / 黑白）
   - 文字 / 卖点标签（点击画布放置，可拖动）
6. 背景替换 / 菜品增强：调用豆包 → 4 张候选 → 显式 confirm → 选中替换画布源图
7. 一键美化按钮 → Pillow API → 结果进入编辑器
8. 撤销 / 重做栈（edit_stack）+ 保存成品（canvas.toDataURL → /save）
9. 真实 API 联调（非 mock）：第一步 Swagger 反查契约文档一致性，不一致回写
10. 单元测试（Vitest）：edit_stack 撤销/重做、滑块参数序列化
11. 视觉一致性检查：同一张图分别走 Pillow 一键美化和前端手动调色，对比观感差异；保存成品以画布所见为准

### 交付物
- 上传图和 AI 图都能编辑，操作实时显示在预览图
- 保存成品到 MinIO，素材库可见
- 429/422 错误提示

---

## D3 — 菜单设计前端 + 集成验证

**目标**：菜单模板选择、菜品勾选、渲染导出全链路。

```
前置：D1 + D2
```

### 任务清单

1. 菜单设计 Tab：模板选择（xhs / a4）
2. ItemPicker：从素材库勾选菜品、排序、分区（招牌/主食/小吃/饮品）
   - 只展示 asset_type=dish 且非派生候选的素材
3. 色系选择：8 色板 + 自定义
4. 渲染预览：调用 /render（带 version），409 冲突处理，展示成品图
5. 导出下载：预签名 URL
6. 菜单 PATCH 乐观锁 409 处理
7. 契约一致性反查：同 D2，先用 Swagger 反查 design-api.md，不一致回写
8. 端到端验证：上传实拍图 → 美化/编辑 → 建菜单 → 渲染 → 导出

### 交付物
- 小红书竖版菜单和 A4 菜单均可完整产出
- 端到端流程可演示

---

## 执行顺序

```
D1 (后端) → D2 (实时编辑器) → D3 (菜单设计)
```

每阶段独立对话，D2/D3 引用 `docs/contracts/design-api.md` 作为接口基线。

## 已知妥协（记录在案）

- A4 300dpi 渲染 MVP 同步执行，超时 60s；渲染服务设计为纯函数，后续切 Celery 只改入口
- 背景替换/菜品增强是"尽力而为"，菜品主体可能有重绘差异，产品预期按氛围可用
- 一键美化默认不做灰度世界白平衡，保留暖光色调；参数需真实餐厅图调优
- 字体文件统一打包进仓库，本地与 Docker 一致
- MVP 只导出 PNG，PDF 印刷导出排后续
- discarded 候选保留不清理，后续加定时 GC
