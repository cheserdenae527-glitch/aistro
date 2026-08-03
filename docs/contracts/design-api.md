# 视觉设计板块 API 契约

> 版本：v0.1 · 对应 D1 后端实现
> 基线：docs/SPEC-DESIGN.md v0.1

所有接口前缀 `/api/v1`，全部需要 JWT（`Authorization: Bearer <token>`），并校验
`project -> shop -> merchant -> user` 所有权；非所有者一律 404。

## 1. 项目

### 1.1 列表

```http
GET /design-projects?shop_id=<uuid>&status=<draft|active|archived>
```

`status` 可选。响应：

```json
[
  {
    "id": "uuid",
    "shop_id": "uuid",
    "title": "小红书菜单",
    "status": "draft",
    "created_at": "2026-08-03T00:00:00Z",
    "updated_at": "2026-08-03T00:00:00Z"
  }
]
```

### 1.2 创建 / 详情 / 更新 / 删除

```http
POST   /design-projects
GET    /design-projects/{project_id}
PATCH  /design-projects/{project_id}
DELETE /design-projects/{project_id}
```

创建 Body：

```json
{ "shop_id": "uuid", "title": "小红书菜单", "status": "draft" }
```

更新 Body 允许 `title` / `status`（可选字段，部分更新）。

## 2. 素材

### 2.1 列表

```http
GET /design-projects/{project_id}/assets
    ?status=<pending|active|discarded>
    &asset_type=<dish|logo|photo>
    &include_derived=<false|true>
```

默认排除 `derived_from_asset_id` 非空的派生候选；`include_derived=true` 时返回全部。

响应项：

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "asset_type": "dish",
  "source": "upload",
  "status": "active",
  "batch_id": null,
  "derived_from_asset_id": null,
  "original_url": "https://...presigned...",
  "processed_url": null,
  "thumb_url": null,
  "edit_stack": null,
  "beauty_config": null,
  "dish_name": "红烧肉",
  "price": "38.00",
  "tagline": "现点现做",
  "created_at": "2026-08-03T00:00:00Z",
  "updated_at": "2026-08-03T00:00:00Z"
}
```

### 2.2 上传 / 更新 / 删除

```http
POST   /design-projects/{project_id}/assets
PATCH  /design-projects/{project_id}/assets/{asset_id}
DELETE /design-projects/{project_id}/assets/{asset_id}
```

上传为 `multipart/form-data`：`file`（png/jpeg/webp，<=10MB，PIL 二次校验）、
`asset_type`、`dish_name`、`price`、`tagline`。上传成功即 `status=active`。

PATCH Body（可选字段）：

```json
{
  "asset_type": "dish",
  "dish_name": "秘制红烧肉",
  "price": "42.00",
  "tagline": "招牌必点"
}
```

删除时若素材被任何 `menu_designs.items` 引用，返回 `409`。

### 2.3 纯文生图 / 带参考图生成

```http
POST /design-projects/{project_id}/assets/generate
```

`multipart/form-data`：`prompt`（必填，敏感词 422）、`ref_image`（可选）、
`asset_type`（可选）。不依赖已有 asset。

频控：60s，key 含 `user_id + shop_id`。豆包返回 4 张后全部落库为
`status=pending`，共享同一 `batch_id`：

```json
{
  "batch_id": "uuid",
  "candidates": [
    { "aid": "uuid", "url": "https://...", "thumb_url": null, "batch_id": "uuid" }
  ]
}
```

### 2.4 候选确认

```http
POST /design-projects/{project_id}/assets/{asset_id}/confirm
```

按 `batch_id` 查询同批：选中记录置 `active`，其余置 `discarded`。
重复确认非 `pending` 记录返回 `409`。

```json
{
  "batch_id": "uuid",
  "active_aid": "uuid",
  "discarded_aids": ["uuid", "uuid", "uuid"]
}
```

### 2.5 一键美化

```http
POST /design-projects/{project_id}/assets/{asset_id}/beautify
```

Body：

```json
{
  "mode": "enhance",
  "brightness": 1.05,
  "contrast": 1.08,
  "saturation": 1.05
}
```

默认 `enhance` 不做灰度世界白平衡，保留暖光色调；`color_correct` 显式白平衡。
结果写入 `processed_url`，频控 30s。

### 2.6 背景替换 / 菜品增强

```http
POST /design-projects/{project_id}/assets/{asset_id}/bg-replace
POST /design-projects/{project_id}/assets/{asset_id}/enhance
POST /design-projects/{project_id}/assets/{asset_id}/ai-beautify
POST /design-projects/{project_id}/assets/{asset_id}/ai-beautify/prompt
```

Body：`{ "prompt": "..." }`。以当前素材为参考图生成 4 张候选，候选
`derived_from_asset_id=当前 aid`、`status=pending`、共享 `batch_id`。
频控 60s。

`ai-beautify` 的 `prompt` 可选：留空时后端使用默认的美食摄影增强提示词
（提升光泽/质感/光影，保留菜品主体与构图）；填写时覆盖默认提示词。

`ai-beautify/prompt` 用 LLM 生成美化提示词（表明侧重点），Body：

```json
{ "focus": "暖色氛围", "dish_name": "红烧肉" }
```

返回 `{ "prompt": "..." }`，频控 20s；前端可编辑后再调用 `ai-beautify`。
`focus` 与 `dish_name` 可选，敏感词返回 422。

### 2.7 保存成品

```http
POST /design-projects/{project_id}/assets/{asset_id}/save
```

Body：

```json
{
  "image_base64": "data:image/png;base64,...",
  "edit_stack": [],
  "beauty_config": {}
}
```

`image_base64` 解码后 <=10MB。保存时折叠派生候选：同项目 `status=active`
且 `derived_from_asset_id=当前 aid` 的记录置为 `discarded`。

## 3. 菜单

### 3.1 CRUD

```http
POST   /design-projects/{project_id}/menus
GET    /design-projects/{project_id}/menus
GET    /design-projects/{project_id}/menus/{menu_id}
PATCH  /design-projects/{project_id}/menus/{menu_id}
```

创建 Body：

```json
{
  "menu_type": "xhs",
  "template_id": "xhs_menu_01",
  "shop_name": "深夜食堂",
  "logo_url": null,
  "color_scheme": {
    "primary": "#D4520A",
    "secondary": "#FFF6EC",
    "accent": "#C93828",
    "text": "#2D1A0A",
    "preset_name": "暖冬橘"
  },
  "items": [
    {
      "asset_id": "uuid",
      "section": "招牌",
      "sort": 1,
      "override_name": null,
      "override_price": null,
      "override_tagline": null
    }
  ]
}
```

模板与类型映射：`xhs_menu_01 -> xhs`、`a4_menu_01 -> a4`；类型与模板不一致时自动纠正。
每个 `asset_id` 必须属于当前项目且 `status=active`，否则 `400`。

PATCH 必须带 `version`；版本不匹配返回 `409`，成功后续版本 +1。

### 3.2 渲染

```http
POST /design-projects/{project_id}/menus/{menu_id}/render
```

Body：`{ "version": 0 }`。版本不匹配 `409`。渲染前再次校验 items 归属与 active，
并从 `design_assets` 实时取值：

```text
override_name  ?? asset.dish_name
override_price ?? asset.price
override_tagline ?? asset.tagline
图片：asset.processed_url ?? asset.original_url
```

成功后 `status=rendered`、`version+1`、`output_url` 为 MinIO 预签名 URL：

```json
{
  "id": "uuid",
  "output_url": "https://...",
  "status": "rendered",
  "version": 1
}
```

## 4. 数据模型

- `design_projects`：id / shop_id / title / status / created_at / updated_at
- `design_assets`：id / project_id / asset_type / source / status / batch_id /
  derived_from_asset_id（FK ON DELETE SET NULL）/ original_url / processed_url /
  thumb_url / edit_stack / beauty_config / dish_name / price / tagline
- `menu_designs`：id / project_id / menu_type / template_id / shop_name / logo_url /
  color_scheme / items / output_url / status / version

## 5. 错误码

| 状态码 | 场景 |
|---|---|
| 400 | 参数/图片/模板/items 校验失败 |
| 401 | 未登录或 token 无效 |
| 404 | 项目/素材/菜单不存在或非所有者 |
| 409 | 乐观锁版本不匹配、重复 confirm、删除被引用素材 |
| 422 | prompt/文本含敏感词 |
| 429 | 频控（generate/edit 60s，beautify 30s） |
| 502 | 豆包生图失败或 MinIO 读取失败 |
