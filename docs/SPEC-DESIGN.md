# AiRestro — 视觉设计板块 设计规约

> 版本：v0.1 · 2026-08-03
> 状态：定稿 · 自成一类模块

---

## 1. 模块定位

独立入口（侧边栏"视觉设计"）。面向运营人员：**上传手机实拍图或使用 AI 生成图，在实时编辑器中完成美化，再排版成菜单成品**。

MVP 输出覆盖：
- 小红书竖版宣传菜单长图（1242×1660，3:4）
- 线下实体菜单 A4（210×297mm，300dpi 导出）

后续可扩展抖音/美团等平台模板，以及更多菜单形态。

---

## 2. 功能范围

### 2.1 实时图片编辑器（核心）

编辑器是板块中心，所有图片（上传或 AI 生成）都进入同一套编辑流程：

```
图片来源 ──┬─ 手机实拍上传
           └─ AI 生成（纯文生图 / 带参考图，豆包）
                │  生成接口不依赖已有 asset，
                │  4 张候选先落库为 pending 记录
                ▼
            用户确认选中 → active，其余 discarded
                │
                ▼
        ┌── 实时编辑画布 ──┐
        │  · 裁剪 / 旋转    │
        │  · 亮度/对比度/  │
        │    饱和度/色温    │
        │  · 滤镜           │
        │  · 背景替换(豆包) │
        │  · 文字/卖点标签  │
        │  · 尺寸模板适配   │
        └────────┬─────────┘
                 │  所有操作实时渲染
                 ▼
            保存成品 → MinIO
```

**关键约束：任何编辑操作必须实时反映到预览图上**，不允许"先保存再回显"的异步流程（背景替换除外，豆包生成本身有等待时间，完成后结果图自动进入编辑器继续编辑）。

### 2.2 一键美化

后端 Pillow 自动管线，秒级返回：
- 自动白平衡（灰度世界）
- 亮度/对比度增强
- 锐化（UnsharpMask）
- 输出压缩（JPEG/WebP quality 85）

一键美化结果进入编辑器，可继续手动微调。

### 2.3 背景替换 / 菜品增强

复用豆包 `_generate_image(prompt, size, ref_data, ref_mime)`：
- 背景替换：ref 图为原图，prompt 描述氛围背景，保留菜品主体
- 菜品增强：ref 图为原图，prompt 提升食物质感/光泽/构图
- 返回 4 张候选，用户选择后进入编辑器

### 2.4 菜品素材库

每个素材可维护：`dish_name` / `price` / `tagline` / 成品图。菜单设计时直接勾选。

### 2.5 菜单设计

选模板 → 勾选菜品素材 → 选色系 → 渲染 → 导出。

MVP 内置模板：
| template_id | 输出 | 规格 |
|---|---|---|
| xhs_menu_01 | 小红书竖版长图 | 1242×1660（3:4），菜品网格 + 价格标签 |
| a4_menu_01 | 线下实体菜单 | A4 300dpi 2480×3508，招牌/主食/小吃/饮品分区 |

色系复用 `COLOR_PRESETS` 8 套预设 + 自定义四色。

---

## 3. 数据模型

### 3.1 design_projects（设计项目）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK → shops | 归属门店 |
| title | varchar(100) | 项目名 |
| status | enum draft / active / archived | |
| created_at / updated_at | timestamptz | |

### 3.2 design_assets（图片素材）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → design_projects | |
| asset_type | enum dish / logo / photo | 素材类型 |
| source | enum upload / ai | 来源 |
| status | enum pending / active / discarded | 生命周期（AI 候选默认 pending） |
| batch_id | UUID nullable | 同一次生成（generate/bg-replace/enhance）的 4 条候选共享；confirm 按此查询同批 |
| derived_from_asset_id | UUID FK → design_assets nullable，ON DELETE SET NULL | 派生来源（bg-replace/enhance 的原图 aid）；原图删除时置空，不影响已 discarded 的派生记录 |
| original_url | text | 源图（上传/AI 原图） |
| processed_url | text | 编辑/美化后成品 |
| thumb_url | text | 缩略图（可选） |
| edit_stack | jsonb | 编辑操作历史（可回放，MVP 可选） |
| beauty_config | jsonb | 一键美化参数 |
| dish_name / price / tagline | | 菜品素材字段 |
| created_at / updated_at | timestamptz | |

### 3.3 menu_designs（菜单设计）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → design_projects | |
| menu_type | enum xhs / a4 | |
| template_id | varchar(50) | 模板标识 |
| shop_name | varchar(100) | 菜单上的店名 |
| logo_url | text | Logo（可选） |
| color_scheme | jsonb | 四色方案 |
| items | jsonb | 菜品配置数组（见下） |
| output_url | text | 渲染成品 |
| status | enum draft / rendered | |
| version | int | 乐观锁 |
| created_at / updated_at | timestamptz | |

`items` 是**实时引用**，不是快照。渲染时从 `design_assets` 实时读取 `dish_name / price / tagline / processed_url`；`override_*` 字段用于本次菜单内的局部覆盖（例如菜单上改价而不改素材库）。已渲染的 `output_url` 是图片快照，不受素材库后续修改影响；再次渲染时使用最新素材值。

**取值优先级（渲染时）**：`override_name ?? asset.dish_name`、`override_price ?? asset.price`、`override_tagline ?? asset.tagline`；图片一律取 `asset.processed_url`，无成品时回退 `original_url`。

`items` 结构：
```json
[
  {
    "asset_id": "uuid",
    "section": "招牌",
    "sort": 1,
    "override_name": null,
    "override_price": null,
    "override_tagline": null
  }
]
```

### 3.4 候选图生命周期

AI 生成（纯文生图、背景替换、菜品增强）统一采用以下流程：

```
豆包返回 4 张 URL
    │
    ▼
全部下载到 MinIO，创建 4 条 design_assets
  (source=ai, status=pending, batch_id=同一次调用生成的 UUID,
   bg-replace/enhance 额外记录 derived_from_asset_id=原图 aid)
    │
    ▼
返回候选列表 [{ aid, url, thumb_url, batch_id }]
    │
    ▼
用户选中 → POST /assets/{aid}/confirm
  · 按 batch_id 查询同批 4 条
  · 选中记录 status=active
  · 同批其余记录 status=discarded
```

- 候选在生成时即落库，因此 `aid` 从一开始就存在，后续编辑/保存不需要特殊分支
- `discarded` 记录 MVP 保留不删除（供审计/回看），后续可加定时 GC
- 前端拿到候选列表后，确认动作必须显式调用 `/confirm`，不能只在前端切换 URL

### 3.5 派生候选与最终成品的归属（confirm 后的数据流）

`bg-replace` / `enhance` 是针对**已存在素材 aid** 发起的派生操作。为避免素材库出现"语义不明的两张图"，规则如下：

1. 生成候选：`derived_from_asset_id = 原 aid`，`batch_id` 同批共享
2. 用户 confirm 选中一张：该候选 `status=active`，同批其余 `discarded`
3. **编辑器画布继续停留在原 aid**：编辑历史（edit_stack）不断，后续裁剪/滤镜/文字都叠加在原 aid 上
4. 最终 `POST /assets/{原aid}/save` 保存成品时，后端查找 `status=active AND derived_from_asset_id=原aid` 的记录，将其折叠为 `discarded`（候选只作为画布源图的中转，成品已落在原 aid）
5. 素材库 UI 对派生记录显示"从 XX 生成"分组标记，折叠后自动隐藏

纯文生图（`/assets/generate`，无原 aid）不触发折叠规则：confirm 选中的候选就是正式素材（无 `derived_from_asset_id`），后续编辑/保存直接作用在该 aid 上。

---

## 4. API

全部接口 JWT 鉴权 + shop 所有权校验（shop → merchant → user），非所有者 404。

### 4.1 项目

```
GET    /api/v1/design-projects?shop_id=&status=
POST   /api/v1/design-projects
GET    /api/v1/design-projects/{id}
PATCH  /api/v1/design-projects/{id}
DELETE /api/v1/design-projects/{id}
```

### 4.2 素材

```
GET    /api/v1/design-projects/{id}/assets?status=active
  → 默认排除 derived_from_asset_id 非空的记录（派生候选是中转态，不进入素材库/ItemPicker）
POST   /api/v1/design-projects/{id}/assets        → FormData 上传，MIME 校验，<=10MB，status=active
PATCH  /api/v1/design-projects/{id}/assets/{aid}  → 更新 dish_name/price/tagline
DELETE /api/v1/design-projects/{id}/assets/{aid}  → 被菜单引用时 409 拦截

POST   /api/v1/design-projects/{id}/assets/generate
  → 纯文生图（Body: { prompt, ref_image? }），不依赖已有 asset
  → 豆包生成 4 张 → 落库 pending（batch_id 同批共享）→ 返回候选列表 [{ aid, url, thumb_url, batch_id }]
  → 频控 60s

POST   /api/v1/design-projects/{id}/assets/{aid}/confirm
  → 确认候选：按 batch_id 查询同批，当前记录 active，其余 discarded
  → 若候选有 derived_from_asset_id，编辑器画布仍留在原 aid
  → 幂等：记录已非 pending（重复 confirm / 已被折叠）时返回 409

POST   /api/v1/design-projects/{id}/assets/{aid}/beautify    → Pillow 一键美化，30s 频控
POST   /api/v1/design-projects/{id}/assets/{aid}/bg-replace  → 豆包背景替换，60s 频控，候选带 derived_from_asset_id + confirm
POST   /api/v1/design-projects/{id}/assets/{aid}/enhance     → 豆包菜品增强，60s 频控，候选带 derived_from_asset_id + confirm
POST   /api/v1/design-projects/{id}/assets/{aid}/save
  → 保存编辑器成品(base64/upload)
  → 折叠：同项目下 status=active 且 derived_from_asset_id=当前 aid 的派生候选置为 discarded
```

### 4.3 菜单

```
POST   /api/v1/design-projects/{id}/menus
  → items 中每个 asset_id 必须属于当前 project_id 且 status=active，否则 400
GET    /api/v1/design-projects/{id}/menus
GET    /api/v1/design-projects/{id}/menus/{mid}
PATCH  /api/v1/design-projects/{id}/menus/{mid}     → version 乐观锁；items asset_id 归属+active 校验同创建
POST   /api/v1/design-projects/{id}/menus/{mid}/render
  → Body: { version }，校验通过后渲染，version 自增
  → 渲染前从 design_assets 实时读取菜品数据
  → 渲染前再次校验 items asset_id 属于当前 project_id 且 status=active，非法返回 400
```

---

## 5. 前端组件树

```
VisualDesignIndexPage（/design）
  └─ 项目列表（按门店分组，可新建）

VisualDesignEditorPage（/design/:id）
  ├─ Tab 素材与编辑
  │   ├─ AssetLibrary（左侧：上传 / AI 生成 / 素材列表）
  │   ├─ ImageEditor（右侧）
  │   │   ├─ CanvasPreview（实时预览，编辑源可来自上传或 AI 生成图）
  │   │   ├─ Toolbar（裁剪 / 旋转 / 滤镜 / 调色 / 文字 / 背景替换 / 尺寸）
  │   │   ├─ PropertyPanel（滑块参数，拖动即实时生效）
  │   │   └─ ActionBar（撤销 / 重做 / 一键美化 / 保存成品）
  │   └─ AiGenerateDrawer（豆包生成：prompt + 参考图 → 4 张候选 → 选一张进入编辑器）
  └─ Tab 菜单设计
      ├─ TemplatePicker（xhs_menu_01 / a4_menu_01）
      ├─ ItemPicker（从素材库勾选菜品 + 排序 + 分区；只展示 asset_type=dish 且非派生候选的素材）
      ├─ ColorSchemePicker（8 色板 + 自定义）
      └─ RenderPanel（渲染预览 / 导出下载）
```

### 编辑器实时预览技术

- 前端 Canvas 按 `edit_stack` 顺序重绘：裁剪 → 旋转 → 滤镜/参数 → 文字
- 滑块操作直接触发重绘（requestAnimationFrame 节流）
- 保存时 `canvas.toDataURL` → POST `/save` → 后端转存 MinIO
- 背景替换是唯一异步操作：等待豆包返回 → 结果图替换画布源图，edit_stack 中记录 `bg_replace` 节点

---

## 6. 技术实现要点

### 6.1 一键美化（Pillow）

```python
def auto_beautify(data: bytes, mode="enhance", brightness=1.05,
                  contrast=1.08, saturation=1.05) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    # mode=enhance（默认）：不做灰度世界白平衡，保留中餐暖光色调
    # mode=color_correct：可选手动触发色彩校正
    # ImageEnhance: brightness / contrast / color
    # ImageFilter.UnsharpMask(radius=2, percent=80, threshold=3)
    # 输出 JPEG quality=85
```

**重要**：灰度世界白平衡默认不启用——它对暖光中餐图容易洗掉暖色调、降低食欲感。`mode=enhance` 只做轻度亮度/对比度/锐化，白平衡作为可选项留给用户。D1 必须拿真实餐厅实拍图验证参数，SPEC 中的数值不是最终值。

### 6.2 菜单渲染（Pillow）

- 模板 JSON 定义布局：画布尺寸、背景色、标题字体/字号、卡片坐标
- 小红书：1242×1660；A4：2480×3508（300dpi）
- 卡片内容：菜品图（裁剪为 3:2 或 1:1 圆角）、名称、价格、卖点
- 中文字体：**打包同一份字体文件进仓库**（`backend/assets/fonts/`），本地和 Docker 用同一份，不依赖系统字体，避免本地/线上渲染字形不一致
- 输出 PNG → MinIO

**性能与架构**：
- 渲染服务实现为**纯函数**（输入配置 + 素材字节 → 输出 PNG 字节），方便后续迁移到 Celery 异步任务
- MVP 同步渲染是已知妥协：A4 300dpi 多菜品拼贴可能 1-5 秒，HTTP 请求超时建议 60s；后续若变慢再切队列
- 已知妥协：MVP 只导出 PNG，线下印刷场景后续需要补 PDF 导出

### 6.3 豆包集成

- 复用 `doubao_image._generate_image`，新增通用入口 `generate_edited(prompt, size, ref_data, ref_mime)`
- prompt 敏感词过滤（复用 `contains_blocked`）
- 频控：beautify 30s，bg-replace/enhance 60s
- **效果预期管理**：背景替换是"尽力而为的氛围替换"，不是精确抠图。菜品主体可能被模型重新生成，颜色/形状存在漂移；产品文案和前端提示必须明示这一点，验收标准按"氛围可用"而非"像素级保留"
- prompt 中追加锚点约束："严格保留参考图中的菜品主体、位置、形状、颜色"

---

## 7. 安全约束

| 接口 | 约束 |
|---|---|
| 全部 | JWT + shop 所有权 |
| upload | MIME png/jpeg/webp，<=10MB，PIL 二次验证 |
| save | base64 解码后 <=10MB |
| assets/generate / bg-replace / enhance | prompt 敏感词 422，频控 60s |
| menu PATCH / render | version 乐观锁，409 |
| delete asset | 被 menu_designs.items 引用时 409 |

频控维度统一为 **user + shop**（key 含 user_id + shop_id），同一门店多运营人员互不干扰。

---

## 8. MVP 边界

### 包含
- 设计项目 CRUD + 素材库
- 实时图片编辑器（上传 / AI 生成图均可进入，操作实时预览）
- 一键美化（Pillow）
- 豆包背景替换 + 菜品增强（带参考图，4 张候选）
- 小红书竖版菜单模板 + A4 模板各 1 套
- 菜单渲染导出（Pillow + 中文字体）
- 鉴权 / 频控 / 敏感词 / 乐观锁

### 不包含
- 抖音/美团菜单模板
- rembg 本地去背景（后续可选，MVP 用豆包背景替换）
- 多人协作 / 历史版本管理
- 批量导入平台菜品
- 动效菜单 / 在线 PDF 排版
