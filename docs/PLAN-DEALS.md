# 团购工坊模块 — 实现计划

> 基于 SPEC-DEALS v0.2 · 独立于主项目里程碑

## 依赖与复用

| 能力 | 来源 | 状态 |
|---|---|---|
| DeepSeek LLM | `app.ai` 客户端模式 | 已有 |
| JWT + shop 所有权 | `app.core.deps` | 已有 |
| MinIO | `app.services.storage` | 已有 |
| design_assets 导出 | 视觉设计模块 | 已有 |
| 敏感词 / 频控 | `app.core` | 已有 |

---

## G1 — 后端：模型 + API + AI 套餐 Agent

**目标**：项目/菜品/竞品/方案/平台文案全部 API 可用，AI 生成三款套餐并支持多平台 copy。

### 任务清单

1. Alembic 迁移：
   - deal_projects / deal_items / competitor_deals / deal_schemes / deal_scheme_copies
   - deal_items.category 枚举（signature/staple/snack/drink）\n   - competitor_deals 含 updated_at
   - deal_schemes 含 generation_batch / is_archived / items 快照 / margin_estimate
   - deal_scheme_copies 唯一约束 (scheme_id, platform)
   - 级联：删除项目 → items/competitor_deals/schemes/copies 全级联
2. SQLAlchemy 模型 + Pydantic Schema
3. API：
   - 项目 CRUD + PATCH + 列表分页
   - 菜品清单 CRUD（category 枚举校验）
   - 竞品套餐 CRUD
   - POST schemes/generate：generation_batch+1，旧批次 is_archived=true；频控失败不计入
   - GET schemes（默认只返回未归档，支持 include_archived）
   - PUT schemes → status=edited
   - POST schemes/{sid}/copy：按 (scheme_id, platform) 覆盖更新，多平台互不影响
   - GET schemes/{sid}/copies
   - POST schemes/{sid}/export-to-design：Body { platform }，未生成该平台 copy 返回 400
4. DealAgent：
   - 套餐生成 prompt（三款结构 + 招牌/高毛利约束）
   - gross_margin + net_margin 计算（平台佣金按项目 platform 取默认值）
   - 负 net_margin 警示逻辑（AI 生成时校验，无法避免则 note 警示）
   - 平台 copy prompt（抖音/美团/小红书差异化）
5. 鉴权 / 频控（成功才计入）/ 敏感词
6. 测试：
   - 生成：3 款类型齐全、招牌菜必含、gross/net_margin 计算正确
   - regenerate：旧批次归档、新批次活跃、edited 方案也被归档
   - 快照：生成后修改菜品清单不影响已生成方案
   - copy：多平台并存、同平台重复生成覆盖、其余平台不受影响
   - export：未生成该平台 copy → 400；正常导出 design_assets
   - 敏感词 422 不占频控；AI 格式错误不占频控
   - 负 net_margin：note 警示但可保存
   - category 枚举越界 400
   - 归档方案的 copies 仍可查询（物理保留，前端只读）\n   - 级联删除验证
   - 鉴权 401 / 跨用户 404
7. 契约文档：`docs/contracts/deals-api.md`
   - 写清 copy 覆盖语义、regenerate 归档语义、净毛利公式、export Body
   - **status 语义**：generated 为历史兼容值，生成逻辑只写 draft / edited，不再写入 generated
   - **负 net_margin**：AI 尽量避免；兜底允许保存并强警示，后端不硬拒绝（与 PLAN 测试一致）
   - **归档方案 copies**：物理保留仍可查询，前端只读

### 交付物
- Swagger 可调用全部 API
- pytest 全绿 + 契约文档

---

## G2 — 前端团购工坊

**目标**：项目 → 菜品/竞品 → 生成方案 → 多平台文案 → 导出全流程可用。

```
前置：G1
```

### 任务清单

1. 路由 `/deals` + `/deals/:id`，侧边栏入口
2. 项目列表（分页）+ 新建（选门店/主平台/价格带）
3. Tab 菜品清单：表格 + 录入表单（category 枚举下拉）+ 图片上传
4. Tab 竞品参考：列表 + 录入
5. Tab 套餐方案：
   - 生成按钮：已有批次时二次确认（"重新生成将归档当前方案，已编辑内容不会带入"）
   - 3 张方案卡片（组合快照 + 原价/团购价 + gross/net 毛利两行 + 佣金率标注）
   - 每卡平台文案 Tab（抖音/美团/小红书独立生成与编辑，互不覆盖）
   - 导出该平台视觉设计跳转
   - 历史批次（归档）只读展开
   - 人工编辑（status → edited）+ 复制上线文案
6. 真实 API 联调：Swagger 反查契约文档，不一致回写
7. 单元测试（Vitest）：毛利展示、平台 Tab 状态、二次确认、归档只读

### 交付物
- 套餐生成到导出全流程可操作
- 多平台文案互不覆盖、429/422 提示

---

## G3 — 集成验证

**目标**：真实数据端到端 + 与视觉设计衔接。

```
前置：G1 + G2
```

### 任务清单

1. 用真实门店菜品清单生成套餐（验证毛利估算）
2. 三平台 copy 各生成一套，确认互不覆盖
3. regenerate 验证归档/新批次
4. 封面导出到视觉设计 → 出图 → 保存
5. 修改菜品清单后确认已生成方案不受影响（快照）
6. 契约一致性反查 + 文档回写

### 交付物
- 完整流水线可演示
- 套餐方案可落地使用

---

## 执行顺序

```
G1 (后端) → G2 (前端) → G3 (集成验证)
```

每阶段独立对话，G2/G3 引用 `docs/contracts/deals-api.md`。

## 已知妥协

- 竞品套餐数据 MVP 手动录入，自动抓取后续接平台爬虫
- 成本为手动录入 + AI 估算，真实毛利需财务校正
- 平台佣金率为行业均值默认值，MVP 不支持门店级实际费率覆盖（人工编辑可改）
- 核销/退款/复购数据回流后续对接口碑与平台
- 商圈价格带自动关联后续扩展

