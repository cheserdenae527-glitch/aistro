# 团购工坊 API 接口契约

> 版本：v1.0 · 2026-08-05
> 基于：SPEC-DEALS v0.2 · PLAN-DEALS G1 交付

## 通用约定

- **Base URL**: `/api/v1`
- **鉴权**: 全部端点需 `Authorization: Bearer <JWT>`
- **归属校验链**: 所有 `/deal-projects/{id}/...` 资源校验 `project -> shop -> merchant -> user`，非所有者一律 404
- **分页**: `page` 默认 1；`page_size` 默认 20，上限 100；响应 `{ items, total, page, size }`
- **价格/金额字段**: JSON 序列化为字符串（如 `"68.00"`），前端按字符串展示或 `Number()` 转换

---

## 1. 项目

### POST /deal-projects
Body：
```json
{
  "shop_id": "uuid",
  "title": "抖音暑期套餐",
  "platform": "douyin",
  "price_band": "人均80"
}
```
- `platform`: `douyin | meituan | xiaohongshu`（主平台，决定默认佣金率语境）
- `price_band`: 可选
- 敏感词 422；`shop_id` 非本人门店 404

### GET /deal-projects?shop_id=&page=&page_size=
当前用户全部项目（可按 shop_id 过滤），按 `updated_at` 倒序。

### GET /deal-projects/{id}
### PATCH /deal-projects/{id}
Body 任意子集：`title` / `platform` / `price_band`（敏感词 422）。
### DELETE /deal-projects/{id}
**级联删除** items / competitor-deals / schemes / scheme_copies（DB `ON DELETE CASCADE`）。

---

## 2. 菜品清单

### POST /deal-projects/{id}/items
Body：
```json
{
  "name": "招牌毛肚",
  "category": "signature",
  "cost_price": 20.0,
  "sale_price": 68.0,
  "is_signature": true,
  "is_high_margin": false,
  "image_url": null
}
```
- `category`: `signature | staple | snack | drink`（枚举越界 → FastAPI 统一 422 校验失败语义，与全站一致）
- `cost_price` 可选（null=未知，毛利估算时由 AI 按品类行业均值估算）；`sale_price` 必填 >0
- 名称敏感词 422

### GET /deal-projects/{id}/items?page=&page_size=
### PATCH /deal-projects/{id}/items/{iid}
任意子集（传 null 表示清空该字段，如 `cost_price`）。
### DELETE /deal-projects/{id}/items/{iid}

---

## 3. 竞品套餐（手动录入）

### POST /deal-projects/{id}/competitor-deals
Body：`{ "name", "price", "items_summary", "note"? }`（文本敏感词 422）
### GET /deal-projects/{id}/competitor-deals?page=&page_size=
### PATCH /deal-projects/{id}/competitor-deals/{cid}
Body 任意子集：`name` / `price` / `items_summary` / `note`（传 null 清空 note，文本敏感词 422）。
### DELETE /deal-projects/{id}/competitor-deals/{cid}

---

## 4. 套餐方案（AI 生成）

### POST /deal-projects/{id}/schemes/generate
- Body：`{}`（佣金率按项目主平台取默认值，见 §7）
- AI 生成 3 款：`hook`（引流款）/ `profit`（利润款）/ `scenario`（场景款）
- **regenerate 语义**：`generation_batch + 1`；旧批次全部 `is_archived=true`（不删除、不回收 UUID），**含已被人工编辑（status=edited）的方案**，编辑内容不会自动带入新批次
- 新 3 款为当前活跃批次，`status=draft`，`is_archived=false`
- 项目 `status` 更新为 `generated`
- **频控 20s**（key = `deals:generate:{user_id}:{shop_id}`）：仅生成成功时计入；422 敏感词失败 / AI 格式错误不占窗口

成功响应 `200`：
```json
{
  "generation_batch": 2,
  "schemes": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "scheme_type": "profit",
      "generation_batch": 2,
      "title": "利润款·双人招牌套餐",
      "description": "招牌+高毛利托底",
      "items": [
        {"item_id": "uuid", "name": "招牌毛肚", "qty": 1, "sale_price": 68.0, "cost_price": 20.0}
      ],
      "original_price": 126.0,
      "deal_price": 88.0,
      "cost_estimate": 45.0,
      "margin_estimate": {
        "gross_margin": 0.4886,
        "platform_commission_rate": 0.06,
        "net_margin": 0.4286,
        "note": ""
      },
      "status": "draft",
      "is_archived": false,
      "created_at": "...",
      "updated_at": "...",
      "copies": []
    }
  ]
}
```

**快照语义**：`items` 中 `name / sale_price / cost_price` 是生成那一刻从 `deal_items` 拷贝的值；此后修改菜品清单不会回溯更新已生成方案。`cost_price` 缺真实值时由 AI 估算并在 `margin_estimate.note` 标注「含 AI 估算成本，请按实际成本校正」。

### GET /deal-projects/{id}/schemes?include_archived=
- 默认只返回未归档方案；`include_archived=true` 返回全部（历史批次）
- 排序：`generation_batch` 倒序 → `created_at` 倒序
- 每个方案内嵌 `copies`（已生成的平台文案）

### PUT /deal-projects/{id}/schemes/{sid}
人工编辑，Body 任意子集：
`title` / `description` / `items`（`[{item_id, name, qty, sale_price, cost_price}]` 快照结构）/ `original_price` / `deal_price` / `cost_estimate` / `margin_estimate`
- **任何成功 PUT 都会把 `status` 置为 `edited`**
- `margin_estimate` 由前端一并提交（如需改佣金率/毛利，直接改该字段）；不传则保持现值
- 文本敏感词 422；归档方案同样可编辑（前端只读展示，后端不硬拒）

### DELETE /deal-projects/{id}/schemes/{sid}
删除单个方案（其 copies 级联删除）。

---

## 5. 平台文案（多平台并存）

### POST /deal-projects/{id}/schemes/{sid}/copy
Body：`{ "platform": "douyin" }`
- 生成该平台差异化 copy + cover_prompt
- **覆盖语义**：按 `(scheme_id, platform)` 唯一约束 upsert，同一平台重复生成 = 覆盖更新，**其余平台不受影响**
- **频控 20s**（key = `deals:copy:{user_id}:{scheme_id}`，与 generate 独立窗口）：仅成功计入
- 敏感词 422 / AI 格式错误 502，均不占窗口

响应：`{ id, scheme_id, platform, title, selling_points, rules, cover_prompt, created_at, updated_at }`

### GET /deal-projects/{id}/schemes/{sid}/copies
列出该方案已生成的全部平台文案（含归档方案的 copies，物理保留、前端只读）。

---

## 6. 导出到视觉设计

### POST /deal-projects/{id}/schemes/{sid}/export-to-design
Body：`{ "platform": "douyin" }`
- 取该平台 `deal_scheme_copies.cover_prompt`；**该平台尚未生成 copy → 400**
- `cover_prompt` 再次过敏感词校验，命中 → 422
- 落库：
  - 新建 `design_projects`（`title=团购工坊导出 · {方案标题}`，`status=active`）
  - 新建 `design_assets`：`asset_type=photo`、`source=deals`、`status=active`、`beauty_config={"cover_prompt": ...}`、`dish_name={项目标题} · {方案标题}`、`tagline={copy.title}`
- 响应：`{ "design_project_id": "uuid", "asset_ids": ["uuid"] }`，前端跳转视觉设计

---

## 7. 毛利口径（SPEC-DEALS §4）

```
gross_margin = (deal_price - 组合成本) / deal_price
net_margin   = (deal_price × (1 - 平台佣金率) - 组合成本) / deal_price
```

- 默认佣金率（行业均值，MVP 不支持门店级费率覆盖，可经 PUT 人工改 `margin_estimate`）：
  - douyin = 0.06，meituan = 0.08，xiaohongshu = 0.05
- `note` 规则：
  - 含 AI 估算成本 → 「含 AI 估算成本，请按实际成本校正」
  - hook 款 → 「引流款核心是拉新到店，毛利允许偏低」
  - `net_margin < 0` → 「净毛利为负：请重新评估组合/定价，确认后再上线」
- **负 net_margin 不硬拒**：AI 生成时尽量避免；若仍无法避免，note 强警示，允许保存（200），是否上线由运营判断

---

## 8. status 语义

| 值 | 含义 |
|---|---|
| `draft` | 生成后的唯一正常状态（G1 生成逻辑只写 draft） |
| `edited` | 人工 PUT 编辑过 |
| `generated` | 仅为历史兼容值，G1 起不再写入 |

---

## 9. 错误码汇总

| 状态码 | 场景 |
|---|---|
| 401 | 未登录 / token 无效 |
| 404 | 资源不存在或非本人（shop/project/item/competitor/scheme） |
| 400 | export 时该平台 copy 未生成；copy 缺 cover_prompt |
| 422 | 敏感词（输入或 AI 输出）、参数/枚举校验失败（不占频控） |
| 429 | 频控 20s（generate/copy 各自独立）或 AI 服务限流 |
| 502 | AI 返回格式错误 / AI 服务不可用（不占频控） |

> 说明：全站采用 FastAPI 默认校验语义，枚举越界（如 category）返回 422 而非 400；PLAN-DEALS 测试清单中的「category 枚举越界 400」按此实现为 422，与 studio/district 等既有模块一致。

