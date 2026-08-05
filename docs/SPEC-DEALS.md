# AiRestro — 团购工坊模块 设计规约

> 版本：v0.2 · 2026-08-05
> 状态：定稿 · 自成一类模块
> v0.2 变更：平台文案改为多平台并存（deal_scheme_copies 子表）；补充佣金后净毛利、regenerate 语义、方案快照语义、项目编辑/级联/分页等接口

---

## 1. 模块定位

独立入口（侧边栏"团购工坊"）。面向代运营团队，把**套餐设计**从拍脑袋变成数据+AI 流水线：

```
菜品清单 + 竞品套餐参考 + 平台
    │
    ▼
AI 生成 3 款套餐方案（引流款 / 利润款 / 场景款）
    │
    ▼
定价锚定 + 毛利估算 + 标题/卖点/使用规则
    │
    ▼
平台文案差异化（抖音 / 美团 / 小红书）
    │
    ▼
封面 prompt → 导出视觉设计出图 → 上线清单
```

核心原则：套餐不是打折，是**决策成本最小化 + 组合利润最大化 + 引流到店**。

---

## 2. 三款套餐结构

| 类型 | 目的 | 设计要点 |
|---|---|---|
| hook（引流款） | 拉新、核销到店、沉淀私域 | 价格低、核销快、必有到店体验价值；毛利可低但别亏 |
| profit（利润款） | 主战场 | 招牌菜必含 + 高毛利菜托底 + 客单价锚定商圈中位 |
| scenario（场景款） | 补时段/场景空位 | 工作日午餐 / 周末专享 / 宵夜；解决"什么时候来" |

AI 生成时强制输出三款，每款至少含 1 道招牌菜 + 1 道高毛利菜（如无高毛利数据则标注）。

---

## 3. 平台差异化

| 平台 | 标题策略 | 卖点策略 | 封面 |
|---|---|---|---|
| 抖音 | 数字+场景+情绪 | "一眼看懂值不值" | 视频/直播货架感，强对比 |
| 美团/点评 | 品类关键词前置 | 价格带 + 评分 | 干净实拍，套餐包含明细 |
| 小红书 | 玩法/仪式感 | 打卡 + 场景种草 | 3:4 种草风，人物/环境氛围 |

同一套餐方案按平台生成独立 copy（标题/卖点/规则/cover_prompt），**多平台版本并存、互不覆盖**。

> 设计决策：`deal_projects.platform` 是项目创建时的**主平台**（决定默认价格带参考、竞品录入的语境），但套餐方案生成后允许运营为其他平台追加生成 copy，用于同一套方案在多平台投放前的对比试写。这就是为什么 §5 的 `schemes/{sid}/copy` 接口要单独传 `platform` 参数——如果不需要多平台并存，这个参数和本节这句话都应删除，改为项目内单平台生成。

---

## 4. 数据模型

### deal_projects（团购项目）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK → shops | |
| title | varchar(100) | 项目名（如"抖音暑期套餐"） |
| platform | enum douyin / meituan / xiaohongshu | 主平台（默认语境，非唯一投放平台，见 §3 说明） |
| price_band | varchar(50) nullable | 价格带（人均80） |
| status | enum draft / generated | |
| created_at / updated_at | timestamptz | |

> 级联：删除 `deal_projects` 时，`deal_items` / `competitor_deals` / `deal_schemes`（及其 `deal_scheme_copies`）均 `ON DELETE CASCADE`。

### deal_items（菜品清单，项目内）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → deal_projects | |
| name | varchar(200) | |
| category | enum signature / staple / snack / drink | 招牌/主食/小吃/饮品（原设计为自由文本，改为枚举以约束前端传值） |
| cost_price | numeric nullable | 成本（毛利估算用） |
| sale_price | numeric | 建议售价 |
| is_signature | boolean | 是否招牌菜 |
| is_high_margin | boolean | 是否高毛利菜 |
| image_url | text nullable | 菜品图（复用 MinIO） |
| created_at / updated_at | timestamptz | |

### competitor_deals（竞品套餐参考，手动录入）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → deal_projects | |
| name | varchar(200) | 竞品套餐名 |
| price | numeric | 售价 |
| items_summary | text | 包含内容描述 |
| note | text nullable | 观察备注 |
| created_at / updated_at | timestamptz | |

### deal_schemes（AI 生成的套餐方案）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → deal_projects | |
| scheme_type | enum hook / profit / scenario | |
| generation_batch | int | 第几次 generate 产生（见下方 regenerate 语义） |
| title | varchar(200) | |
| description | text | |
| items | jsonb | [{ item_id, name, qty, sale_price, cost_price }]（生成时快照，见下方说明） |
| original_price | numeric | 原价锚定 |
| deal_price | numeric | 团购价 |
| cost_estimate | numeric nullable | 成本估算 |
| margin_estimate | jsonb | { gross_margin, platform_commission_rate, net_margin, note }（见下） |
| status | enum draft / edited / generated | **draft**=生成后唯一正常状态；**edited**=人工 PUT 编辑过；**generated** 仅为历史兼容值，此后不会再被写入（G1 生成逻辑只写 draft / edited） |
| is_archived | boolean default false | regenerate 产生新方案时，旧批次标记为归档而非删除。归档方案下挂的 deal_scheme_copies **物理保留仍可查询**，前端只读展示 |
| created_at / updated_at | timestamptz | |

> **快照语义**：`items` 中的 `name/sale_price/cost_price` 是生成那一刻从 `deal_items` 拷贝的值，此后菜品清单被修改（改价、取消招牌标记等）**不会**回溯更新已生成的方案。若要反映最新菜价，需要重新生成或人工编辑该方案。`item_id` 仅用于溯源，前端展示一律以快照字段为准。

`margin_estimate` 结构：
```json
{
  "gross_margin": 0.42,
  "platform_commission_rate": 0.06,
  "net_margin": 0.36,
  "note": "估算，请按实际成本校正"
}
```
- `gross_margin = (deal_price - 组合成本) / deal_price`
- `net_margin = (deal_price × (1 - platform_commission_rate) - 组合成本) / deal_price`
- `platform_commission_rate` 按项目 `platform` 取行业均值预置（抖音/美团/小红书可配置不同默认值），MVP 阶段不支持门店级实际费率覆盖，允许人工编辑该方案时手动改这个值。

### deal_scheme_copies（方案的平台文案，一个方案可对应多个平台）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| scheme_id | UUID FK → deal_schemes | |
| platform | enum douyin / meituan / xiaohongshu | |
| title | varchar(200) | |
| selling_points | jsonb | string[] |
| rules | text | |
| cover_prompt | text | 该平台的封面生图 prompt |
| created_at / updated_at | timestamptz | |

唯一约束：`(scheme_id, platform)`，同一方案同一平台再次生成 copy 视为**覆盖更新**（而非追加新记录），不同平台互不影响。

示例：
```json
{
  "platform": "douyin",
  "title": "9.9吃招牌！现炒火锅单人餐",
  "selling_points": ["现炒底料", "30分钟出餐", "午市通用"],
  "rules": "仅限周一至周五午餐，每桌限用1份",
  "cover_prompt": "..."
}
```

---

## 5. API

全部 JWT 鉴权 + shop 所有权校验。

```
POST /api/v1/deal-projects                      → 创建
GET  /api/v1/deal-projects?shop_id=&page=&page_size=  → 列表（分页）
GET  /api/v1/deal-projects/{id}                 → 详情
PATCH /api/v1/deal-projects/{id}                → 编辑（title/platform/price_band）
DELETE /api/v1/deal-projects/{id}               → 级联删除 items/competitor-deals/schemes/copies

POST /api/v1/deal-projects/{id}/items           → 菜品录入
GET  /api/v1/deal-projects/{id}/items?page=&page_size=
PATCH /api/v1/deal-projects/{id}/items/{iid}
DELETE /api/v1/deal-projects/{id}/items/{iid}

POST /api/v1/deal-projects/{id}/competitor-deals → 竞品套餐录入
GET  /api/v1/deal-projects/{id}/competitor-deals?page=&page_size=
DELETE /api/v1/deal-projects/{id}/competitor-deals/{cid}

POST /api/v1/deal-projects/{id}/schemes/generate
  → Body: {}（用项目 platform 取默认佣金率）
  → AI 生成 3 款（hook/profit/scenario），generation_batch + 1
  → **regenerate 语义**：旧批次全部 is_archived=true（不删除、不回收 UUID），新生成 3 款为当前活跃批次；GET schemes 默认只返回未归档的，加 `?include_archived=true` 可查历史批次
  → 已被人工编辑（status=edited）的方案本次 regenerate 仍会被归档——编辑内容不会自动带入新批次，前端需在触发前二次确认
  → 频控 20s（仅生成成功时计入；422 敏感词校验失败或 AI 返回格式错误不占用频控窗口）
GET  /api/v1/deal-projects/{id}/schemes?include_archived=
PUT  /api/v1/deal-projects/{id}/schemes/{sid}   → 人工编辑，status → edited
DELETE /api/v1/deal-projects/{id}/schemes/{sid}

POST /api/v1/deal-projects/{id}/schemes/{sid}/copy
  → Body: { platform }
  → 生成该平台差异化 copy + cover_prompt，写入/更新 deal_scheme_copies（按 scheme_id+platform 覆盖，其余平台不受影响）
  → 频控 20s（同上，失败不计入）
GET  /api/v1/deal-projects/{id}/schemes/{sid}/copies       → 列出该方案已生成的各平台文案
POST /api/v1/deal-projects/{id}/schemes/{sid}/export-to-design
  → Body: { platform }（取该平台对应 deal_scheme_copies.cover_prompt；若该平台尚未生成 copy，返回 400）
  → 把 cover_prompt 写入 design_assets（asset_type=photo, source=deals）
  → 返回 design_project_id，前端跳转视觉设计
```

### AI 生成输入

- 菜品清单（名称/成本/售价/招牌/高毛利）
- 竞品套餐（名称/价格/内容）
- 门店品类 + 价格带 + 平台

### 毛利估算

详见 §4 `deal_schemes.margin_estimate` 结构；同时计算 `gross_margin`（不含平台佣金）与 `net_margin`（扣除平台佣金后）。
- 无成本数据时：AI 按品类行业均值估算，note 标注"估算，请按实际成本校正"
- hook 款允许低毛利甚至 net_margin 接近 0，note 提示"核心是拉新到店"\n- **net_margin 为负**：AI 生成时应尽量避免（通过调整组合/定价）；若仍无法避免，note 必须强警示，允许人工确认后保存。**后端不硬性拒绝**，是否上线由运营判断

---

## 6. 前端

```
DealIndexPage（/deals）→ 项目列表 + 新建（选门店 + 平台 + 价格带）
DealEditorPage（/deals/:id）
├─ Tab 菜品清单
│   ├─ 表格：名称/品类/成本/售价/招牌/高毛利
│   ├─ 录入表单 + 图片上传
├─ Tab 竞品参考
│   ├─ 竞品套餐列表（名称/价格/内容/备注）
├─ Tab 套餐方案
│   ├─ [生成方案]（若已存在未归档批次或存在 edited 方案，弹二次确认："重新生成将归档当前方案，已编辑内容不会带入新方案"）
│   │   → 3 张方案卡片（hook/profit/scenario）
│   ├─ 每张卡片
│   │   ├─ 组合明细 + 原价/团购价 + 毛利（gross/net 两行，标注佣金率）
│   │   ├─ 平台文案 Tab 切换（抖音/美团/小红书，各自独立生成与编辑，互不覆盖）
│   │   └─ [生成该平台文案] [导出该平台视觉设计]
│   ├─ 历史批次（归档）可展开查看，只读
│   └─ 人工编辑 + 复制上线文案
```

---

## 7. 安全约束

| 接口 | 约束 |
|---|---|
| 全部 | JWT + shop 所有权 |
| schemes/generate | 敏感词 422；频控 20s（user+shop，仅成功计入） |
| schemes/{sid}/copy | 敏感词 422；频控 20s（同上，按 scheme_id 维度独立计频，不与 generate 共用窗口） |
| export-to-design | 复用 design 所有权；cover_prompt 敏感词校验；platform 对应 copy 不存在时 400 |
| 菜品/竞品录入 | 文本敏感词校验 |

---

## 8. MVP 边界

### 包含
- 项目 / 菜品清单 / 竞品套餐参考 CRUD
- AI 生成 3 款套餐方案（组合 + 定价 + 毛利 + 标题卖点规则）
- 平台差异化 copy 生成 + 封面 prompt
- 导出到视觉设计出图
- 人工编辑 + 上线文案复制

### 不包含
- 自动抓取平台套餐数据（后续接美团/点评/抖音爬虫）
- 自动核算真实成本（MVP 手动录入 + AI 估算）
- 核销/退款/复购数据回流（后续对接口碑与平台）
- 商圈竞品价格带自动关联（后续商圈快照扩展）
- 套餐 A/B 对比 / 多版本管理

---

## 9. 复用清单

| 能力 | 来源 |
|---|---|
| DeepSeek LLM | `app.ai` 客户端模式 |
| JWT + shop 所有权 | `app.core.deps` + 现有 helper |
| MinIO | `app.services.storage` |
| design_assets 导出 | 视觉设计模块 |
| 敏感词 / 频控 | `app.core` |
| 商圈分析 | 后续扩展竞品价格带关联 |

