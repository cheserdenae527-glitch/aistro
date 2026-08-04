# AiRestro — 内容工坊模块 设计规约

> 版本：v0.1 · 2026-08-04
> 状态：定稿 · 自成一类模块

---

## 1. 模块定位

独立入口（侧边栏"内容工坊"）。把**文案生成**和**小红书卡组生成**串成一条生产流水线，产出保存进视觉设计素材库后可继续编辑。

能力来源（已拷贝进 `skills/`）：
- 文案：改编 Viral Writer 的 11 个内容洞见维度 + 小红书平台规范
- 卡组：改编 Guizang Social Card 的 Editorial / Swiss 视觉系统、色板、QA 规则

> **许可提示**：Guizang 为 AGPL-3.0 + 商业授权（10 万起），Viral Writer 无 LICENSE。当前本地使用；对外商用前需联系原作者授权。本项目保留原许可文件于 `skills/` 供溯源。

---

## 2. 核心流程

```
创建项目（绑定门店）
    │
    ▼
Step 1 文案生成
  输入：品类 / 风格 / 价格带 / 主题 / 店名
  输出：5 个标题 + 正文 + 标签 + 配图指导 + 分页素材
    │
    ▼
Step 2 卡组生成
  输入：文案 + 素材图（素材库引用 / 直接上传）+ 模板 + 色板 + 页数(4-8)
  渲染：HTML 模板 → Playwright 截图 1080×1440 PNG
  质检：4-band 密度 + 溢出检查
    │
    ▼
Step 3 保存
  卡组图片存 MinIO
  一键导出到视觉设计素材库 → 进入编辑器微调
```

---

## 3. 文案生成（Viral Writer 化）

`POST /studio/projects/{id}/copy/generate`：

- 调用 DeepSeek，prompt 基于 11 个内容洞见维度：核心观点、副观点、说服策略、情绪触发、金句、情感曲线、情感层次、论证多样性、视角转化、语言风格、互动钩子
- 小红书平台规范：标题 ≤20 字、正文 300-800 字、emoji 分段、5-10 标签、口语化
- 输出结构：

```json
{
  "titles": [
    { "text": "周末必去！人均80的市井火锅", "strategy": "痛点共鸣" }
  ],
  "body": "……（300-800 字，含分段）",
  "tags": ["成都美食", "火锅探店", "人均80"],
  "image_guide": {
    "cover_prompt": "……",
    "pages": [{ "position": "第1段后", "purpose": "辅助说明", "prompt": "……" }]
  }
}
```

- 敏感词校验（复用 `contains_blocked`），命中 422
- 频控 20s（key 含 user_id + shop_id）

---

## 4. 卡组生成（Guizang 化）

### 4.1 分页结构

`deck/generate` 时按所选 `page_count(4-8)` 调用 DeepSeek 把正文拆成每页结构：

```json
{
  "page_specs": [
    { "title": "手工现炒底料", "bullets": ["每天现炒", "0 预制料包", "麻辣鲜香"], "image_index": 0 },
    { "title": "人均80吃到撑", "bullets": ["双人套餐 168", "招牌毛肚必点"], "image_index": 1 }
  ]
}
```

- 每页 1 个观点；标题 12-30 字；要点 2-4 条
- `image_index` 映射素材图顺序（无图则纯文字页）

### 4.2 渲染

- 画布：1080×1440（3:4）
- 安全区：左右 72-96px、上 72-112px、下 80-120px
- 模板：Editorial / Swiss 两套，从 `skills/guizang-social-card-skill/assets/template-*.html` 读取并参数化
- 色板：移植 skill 的 theme-presets（Editorial 6 套 + Swiss 4 套）
- 流程：每页生成 HTML → Playwright `viewport 1080×1440` → `screenshot` PNG → MinIO
- 封面结构：大标题钩子 + 一张主图 + 底部 3-5 个要点条
- 内容页：一页一观点，标题 + 2-4 要点 + 图

### 4.3 QA（移植 validate-social-deck 核心）

每张图渲染后自动检查：

| 检查 | 方法 | 通过标准 |
|---|---|---|
| 4-band 密度 | PIL 分析 PNG，按 360px 水平带统计内容像素 | 内容带覆盖 ≥75% 画布高；无连续两条 justified-empty 带；单空带 ≤15% |
| 溢出 | Playwright evaluate `scrollHeight <= 1440` | 无溢出 |
| 底部空白 | 内容底距画布底 ≤ 安全区 | 不过度留白 |

`qa_report` 存每页结果（pass/fail + 指标），失败页在响应中标记，前端提示重新生成或换页数。

---

## 5. 数据模型

### studio_projects

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK → shops | |
| title | varchar(100) | 项目名 |
| status | enum draft / generated | |
| created_at / updated_at | timestamptz | |

### studio_copies（文案记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → studio_projects | |
| input_payload | jsonb | 品类/风格/价格/主题/店名 |
| titles | jsonb | 5 标题 + 策略 |
| body | text | 正文 |
| tags | jsonb | 标签 |
| image_guide | jsonb | 配图指导 |
| created_at | timestamptz | |

### studio_decks（卡组记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → studio_projects | |
| copy_id | UUID FK → studio_copies | |
| template | enum editorial / swiss | |
| theme | varchar(50) | 色板名 |
| page_count | int | 4-8 |
| page_specs | jsonb | 分页结构 |
| source_assets | jsonb | [{ source: design/upload, asset_id?, url }] |
| images | jsonb | [{ page, url, width, height }] |
| qa_report | jsonb | 每页 QA 结果 |
| status | enum draft / rendered / failed | |
| error_message | text | |
| created_at / updated_at | timestamptz | |

---

## 6. API

全部 JWT 鉴权 + shop 所有权校验。

```
POST  /api/v1/studio/projects                  → 创建
GET   /api/v1/studio/projects?shop_id=         → 列表
GET   /api/v1/studio/projects/{id}             → 详情（含 copies/decks）
DELETE /api/v1/studio/projects/{id}

POST  /api/v1/studio/projects/{id}/copy/generate
  → Body: { category, style, price_range, topic, shop_name }
  → 敏感词 422；频控 20s

POST  /api/v1/studio/projects/{id}/decks
  → 两种素材来源：
     1) JSON: { copy_id, template, theme, page_count, asset_ids[] }
     2) multipart: files[]（直接上传）+ 表单字段
  → 分页 LLM → 渲染 → QA → MinIO
  → 频控 60s（Playwright 重）
  → 返回 { deck_id, images[], qa_report }

GET   /api/v1/studio/decks/{deck_id}           → 卡组详情
POST  /api/v1/studio/decks/{deck_id}/export-to-design
  → 卡组图片写入 design_assets（asset_type=photo, source=studio）
  → 返回 { design_project_id, asset_ids }
```

校验：
- `page_count` 4-8，越界 400
- `asset_ids` 必须属于当前 shop 的 design_projects（所有权 + active）
- 上传图片 MIME png/jpeg/webp，≤10MB/张，单次 ≤8 张

---

## 7. 前端

```
StudioIndexPage（/studio）
  └─ 项目列表 + 新建（选门店）

StudioEditorPage（/studio/:id）
  ├─ Step 1 文案
  │   ├─ 表单（品类/风格/价格/主题/店名）
  │   ├─ [生成文案] → 5 标题卡片（选一个）+ 正文编辑 + 标签
  │   └─ 保存 copy
  ├─ Step 2 卡组
  │   ├─ 模板选择（Editorial / Swiss 视觉缩略卡）
  │   ├─ 色板选择（主题色卡）
  │   ├─ 页数 4-8
  │   ├─ 素材：素材库 Drawer（design_assets 选择）+ 直接上传
  │   └─ [生成卡组] → loading → 卡组横滑预览 + QA 标记
  └─ Step 3 导出
      └─ [导出到视觉设计] → 跳转 /design/:id
```

---

## 8. 安全约束

| 接口 | 约束 |
|---|---|
| 全部 | JWT + shop 所有权 |
| copy/generate | 敏感词 422；频控 20s |
| decks | 频控 60s；page_count 4-8；素材所有权校验 |
| upload files | png/jpeg/webp，≤10MB/张，≤8 张 |
| export-to-design | 复用 design 所有权 |

---

## 9. MVP 边界

### 包含
- 项目 CRUD
- 小红书文案生成（5 标题 + 正文 + 标签 + 配图指导）
- Editorial / Swiss 卡组渲染（1080×1440，4-8 页）
- 素材两种来源（素材库引用 / 直接上传）
- 自动 QA（4-band 密度 + 溢出）
- 导出到视觉设计素材库

### 不包含
- 小红书发布（后续可接 RedBookSkills）
- 公众号 21:9/1:1 封面（后续）
- Live Photo 实况照片（后续）
- 抖音/其他平台模板
- 自定义模板编辑器

---

## 10. 复用清单

| 能力 | 来源 |
|---|---|
| DeepSeek LLM | `app.ai` 现有客户端模式 |
| MinIO | `app.services.storage` |
| 素材库查询/导出 | `design_assets` / `design_projects` |
| 敏感词 / 频控 | `app.core` |
| 视觉设计编辑器 | 导出后跳转微调 |
| 模板与校验规则 | `skills/guizang-social-card-skill/assets` + `references` |
| 文案方法论 | `skills/viral-writer-skill/SKILL.md` |
