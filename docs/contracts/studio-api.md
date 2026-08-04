# 内容工坊板块 API 契约

> 版本：v0.1 · 对应 S1 后端实现
> 基线：docs/SPEC-CONTENT-STUDIO.md v0.1

所有接口前缀 `/api/v1`，全部需要 JWT（`Authorization: Bearer <token>`），并校验
`project -> shop -> merchant -> user` 所有权；非所有者一律 404。

## 1. 项目

### 1.1 创建 / 列表 / 详情 / 更新 / 删除

```http
POST   /studio/projects
GET    /studio/projects?shop_id=<uuid>
GET    /studio/projects/{project_id}
PATCH  /studio/projects/{project_id}
DELETE /studio/projects/{project_id}
```

创建 Body：

```json
{ "shop_id": "uuid", "title": "小红书卡组" }
```

更新 Body 允许 `title` / `status`（`draft | generated`）。

详情响应在项目字段基础上附带 `copies` 与 `decks`：

```json
{
  "id": "uuid",
  "shop_id": "uuid",
  "title": "小红书卡组",
  "status": "draft",
  "created_at": "…",
  "updated_at": "…",
  "copies": [ { "id": "uuid", "project_id": "uuid", "input_payload": {}, "titles": [], "body": "…", "tags": [], "image_guide": {}, "created_at": "…" } ],
  "decks": [ { "id": "uuid", "project_id": "uuid", "copy_id": "uuid", "template": "editorial", "theme": "ink-classic", "page_count": 4, "page_specs": [], "source_assets": [], "images": [], "qa_report": null, "status": "rendered", "error_message": null, "created_at": "…", "updated_at": "…" } ]
}
```

`decks[].images[].url` 与 `decks[].source_assets[].url` 已转为预签名 URL。

## 2. 文案生成

### 2.1 生成

```http
POST /studio/projects/{project_id}/copy/generate
```

Body：

```json
{
  "category": "市井火锅",
  "style": "烟火气",
  "price_range": "人均80",
  "topic": "藏在巷子里的宝藏火锅",
  "shop_name": "蜀香里火锅"
}
```

约束：
- 任意输入字段命中敏感词 → `422`
- 频控 20s（key 含 user_id + shop_id）→ `429`
- DeepSeek 输出结构非法 / 数量不符 → `502`

响应（生成即持久化，返回 copy 记录）：

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "input_payload": { "category": "市井火锅", "…": "…" },
  "titles": [ { "text": "周末必去！人均80的市井火锅", "strategy": "痛点共鸣" } ],
  "body": "……（300-800 字）",
  "tags": ["成都美食", "火锅探店"],
  "image_guide": {
    "cover_prompt": "封面图提示词",
    "pages": [ { "position": "第1段后", "purpose": "辅助说明", "prompt": "配图提示词" } ]
  },
  "created_at": "…"
}
```

### 2.2 更新

```http
PATCH /studio/copies/{copy_id}
```

Body 允许 `titles` / `body` / `tags` / `image_guide`（可选字段，部分更新），用于前端编辑后保存。

### 2.3 配图提示词丰富

```http
POST /studio/copies/{copy_id}/image-prompt/enrich
```

Body：`{ "direction": "配图指导方向（如封面/某页配图的原始 prompt）" }`。

服务端先提炼配图指导的核心想法，再结合该文案的门店信息（品类/风格/价格带/主题/店名），
扩写成一条可直接交给生图模型的中文提示词（覆盖主体/场景/光线/构图/氛围/色彩/质感/画幅）。

响应：

```json
{ "main_idea": "一句话核心想法", "prompt": "100-200 字完整生图提示词" }
```

约束：
- `direction` 命中敏感词 → `422`
- 频控 20s（key 含 user_id + copy_id）→ `429`
- DeepSeek 限流 → `429`、网络/服务错误 → `502`

## 3. 卡组生成

### 3.1 JSON 模式（引用素材库）

```http
POST /studio/projects/{project_id}/decks
Content-Type: application/json
```

Body：

```json
{
  "copy_id": "uuid",
  "template": "editorial",
  "theme": "ink-classic",
  "page_count": 4,
  "asset_ids": ["uuid", "uuid"]
}
```

### 3.2 multipart 模式（直接上传素材）

```http
POST /studio/projects/{project_id}/decks
Content-Type: multipart/form-data
```

表单字段 `copy_id` / `template` / `theme` / `page_count` / `asset_ids`（JSON 数组字符串，可选），
文件字段 `files`（可多个）。素材库引用与直接上传可同时使用，素材总数 ≤8。

约束：
- `template` 仅 `editorial | swiss`，否则 `400`
- `page_count` 4-8，越界 `400`
- 未知色板 `400`
- `asset_ids` 必须属于当前 shop 的 design_projects（`active` 或 AI 生成的 `pending` 候选），否则 `404`
- 上传图片 MIME png/jpeg/webp、≤10MB/张、单次 ≤8 张，否则 `400`
- 素材（引用 + 上传）总数 ≤8，否则 `400`
- `copy_id` 必须属于该项目，否则 `400`
- 频控 60s → `429`
- 分页 LLM 结构非法 → `502`

响应（同步渲染，10-30s）：

```json
{
  "deck_id": "uuid",
  "status": "rendered",
  "images": [
    { "page": 1, "url": "https://…presigned…", "width": 1080, "height": 1440 }
  ],
  "qa_report": {
    "all_pass": true,
    "pages": [
      {
        "page": 1,
        "pass": true,
        "checks": {
          "density": { "pass": true, "coverage": 81.1, "bands": [58.9, 90.0, 100.0, 75.6], "issues": [] },
          "overflow": { "pass": true, "overflow_px": 0 },
          "bottom_blank": { "pass": true, "bottom_gap_px": 112 }
        },
        "issues": []
      }
    ]
  },
  "error_message": null
}
```

渲染失败时 `status=failed` 且携带 `error_message`（HTTP 仍为 200，前端据此提示）。
QA 失败的页 `pass=false` 并在 `issues` 标注，卡组仍为 `rendered`。

### 3.3 卡组详情

```http
GET /studio/decks/{deck_id}
```

返回与项目详情中 deck 结构一致，`images` / `source_assets` 的 url 为预签名 URL。

## 4. 导出到视觉设计

```http
POST /studio/decks/{deck_id}/export-to-design
```

约束：
- 卡组必须已渲染（`status=rendered`），否则 `400`

行为：自动创建一个绑定同 shop 的 design_project（标题 `内容工坊导出 · <项目名>`），
把每页卡组 PNG 写入 `design_assets`（`asset_type=photo`、`source=studio`、`status=active`）。

响应：

```json
{ "design_project_id": "uuid", "asset_ids": ["uuid", "uuid", "…"] }
```

## 5. 错误码汇总

| 场景 | 状态码 |
|---|---|
| 未登录 / token 无效 | 401 |
| 资源不存在或跨用户 | 404 |
| 输入含敏感词 | 422 |
| page_count 越界 / 未知色板 / 上传校验失败 | 400 |
| 文案/卡组频控（20s/60s） | 429 |
| LLM 结构非法 | 502 |
| DeepSeek 自身限流（RateLimitError） | 429 |
| DeepSeek 网络/服务错误（APIError） | 502 |
| 导出未渲染卡组 | 400 |

## 6. 与 SPEC 差异说明

- `copy/generate` 生成即持久化（返回 copy 记录），并额外提供 `PATCH /studio/copies/{id}` 支持编辑后保存。
- multipart 卡组接口额外接受 `asset_ids`，素材库引用与直接上传可同时使用（SPEC 为二选一，S2 联调时为 UX 增强）。
- 素材来源支持 AI 生图：前端改用**异步任务** `POST /design-projects/{id}/assets/generate/job` + `GET /design-projects/{id}/jobs/{job_id}` 轮询，生成 4 张 pending 候选，选中后以 `asset_ids` 传入卡组接口（卡组接口接受 pending 候选）。提示词默认取自 `image_guide.cover_prompt` 且可编辑；点击配图指导标签或「丰富提示词」会先调用 `image-prompt/enrich` 提炼核心想法并扩写成完整提示词，再用于生图。
- 生图进度：豆包流式逐张返回（`partial_succeeded` 事件），job 运行中 `result` 携带 `progress`（0-100）与 `stage`（如「已生成 2/4 张」），前端轮询展示进度条；成功后 `result` 为 `{ batch_id, candidates }`。
- 渲染模板抽取自 `skills/guizang-social-card-skill/assets/template-*.html`，适配为可参数化单页模板（`backend/assets/studio/`），视觉系统（色板/字体/排版）保持一致。
- 卡组渲染为同步执行（`asyncio.to_thread` 不阻塞事件循环），4-8 页约 10-30 秒；MVP 接受，后续可切任务队列。
