# 装修模块 API 接口契约

> 版本：v1.0 · 2026-07-31
> 基于：SPEC-PROFILE.md v0.2 · P1 交付

---

## 通用约定

- **Base URL**: `/api/v1`
- **鉴权**: 所有端点均需 `Authorization: Bearer <JWT>` header
- **Content-Type**: `application/json`（除上传接口用 `multipart/form-data`）
- **Shop 所有权**: 所有 `shop_id` 路径参数会校验 `shop -> merchant -> user` 链，非所有者返回 404
- **分页**: 暂无（单条记录）

---

## 1. 装修数据

### GET /shops/{shop_id}/profiles/{platform}

返回当前装修快照。无记录时自动创建空 draft。

**路径参数**:
| 参数 | 类型 | 说明 |
|---|---|---|
| shop_id | UUID | 门店 ID |
| platform | string | 平台，当前仅 `xiaohongshu` |

**响应**: `200 ProfileResponse`

```json
{
  "id": "uuid",
  "shop_id": "uuid",
  "platform": "xiaohongshu",
  "nickname": "蜀味·市井火锅",
  "bio": "手工现炒底料 | 市井烟火气",
  "avatar_url": "http://...",
  "avatar_original_url": "http://...",
  "avatar_gen_prompt": "...",
  "bg_image_url": "http://...",
  "bg_original_url": "http://...",
  "bg_gen_prompt": "...",
  "color_primary": "#C93828",
  "color_secondary": "#FFF0EE",
  "color_accent": "#A82015",
  "color_text": "#2A0A08",
  "color_mode": "preset",
  "color_preset_name": "江湖红",
  "ai_input_category": "火锅",
  "ai_input_style": "市井烟火",
  "ai_input_price": "人均80",
  "ai_variants": { "variants": [...] },
  "bio_flagged": false,
  "status": "draft",
  "version": 3,
  "created_at": "2026-07-31T...",
  "updated_at": "2026-07-31T..."
}
```

**字段说明**:
- `avatar_url` / `bg_image_url`: 裁剪后图片（预签名 URL，1 小时有效）
- `avatar_original_url` / `bg_original_url`: 原图（生成/上传后写入，预签名 URL）
- `bio_flagged`: 简介是否被敏感词标记
- `version`: 乐观锁版本号，PUT 时必须传入
- `ai_variants`: 最新一次 AI 生成的 4 套方案 JSON

---

### PUT /shops/{shop_id}/profiles/{platform}

保存草稿。**必须携带 `version`**。

**请求体**: `ProfileUpdate`
```json
{
  "nickname": "蜀味·市井火锅",
  "bio": "手工现炒底料 | 市井烟火气",
  "color_primary": "#C93828",
  "color_secondary": "#FFF0EE",
  "color_accent": "#A82015",
  "color_text": "#2A0A08",
  "color_mode": "preset",
  "color_preset_name": "江湖红",
  "version": 3
}
```

**校验规则**:
| 字段 | 约束 |
|---|---|
| nickname | <= 20 字符，禁止 emoji，禁止敏感词 → 422 |
| bio | <= 100 字符，允许 emoji，禁止敏感词 → 422 |
| color_* | `#[0-9A-Fa-f]{6}` |
| version | int，与服务端当前值不匹配 → 409 |

**错误码**:
| 状态码 | 说明 |
|---|---|
| 200 | 成功，返回更新后的 profile |
| 409 | version 冲突，需刷新重试 |
| 422 | 参数校验失败 |

**bio_flagged 语义**:
- PUT bio 时服务端检测敏感词，若命中设置 `bio_flagged=true`
- GET 响应中返回 `bio_flagged` 字段供前端判断

---

## 2. AI 方案生成

### POST /shops/{shop_id}/profiles/{platform}/generate

调用 GPT-4o 一次性生成 4 套完整装修方案。

**请求体**: `GenerateRequest`
```json
{
  "category": "火锅",
  "style": "市井烟火感",
  "price_range": "人均80"
}
```

**响应**: `200 GenerateResponse`
```json
{
  "variants": [
    {
      "id": "A",
      "color_scheme": {
        "primary": "#C93828",
        "secondary": "#FFF0EE",
        "accent": "#A82015",
        "text": "#2A0A08",
        "preset_name": "江湖红"
      },
      "nickname_options": ["蜀味·市井火锅", "蜀味老火锅（玉林店）", "蜀味 火锅铺"],
      "bio": "手工现炒底料 | 市井烟火气 | 人均80吃到撑",
      "avatar_prompt": "A round hot pot logo design...",
      "bg_prompt": "Warm-toned hot pot top view...",
      "filtered": false
    }
  ],
  "generated_at": "2026-07-31T..."
}
```

**频控**: 同 `shop_id + platform` 20 秒内只能调用 1 次
| 状态码 | 说明 |
|---|---|
| 200 | 成功 |
| 422 | category/style 含敏感词 |
| 429 | 频控触发，提示 "20 秒后重试" |
| 500 | LLM 调用失败 |

**要点**:
- 每次调用**覆盖** `ai_variants` 字段
- `filtered: true` 表示该方案所有 nickname 被过滤 + bio 被标记，前端跳过展示
- 敏感词过滤对 LLM 输出后处理：nickname 剔除违规项，bio 替换为 "[内容待审核]"

---

## 3. 图片生成（豆包）

### POST /shops/{shop_id}/profiles/{platform}/generate-avatar

豆包生成头像图（2048x2048）。

**请求体**: `ImageGenerateRequest`
```json
{ "prompt": "A round hot pot logo design..." }
```

**响应**: `200 ImageGenerateResponse`
```json
{
  "url": "http://...",
  "prompt": "A round hot pot logo design...",
  "options": [
    { "object_name": "profiles/abc", "url": "http://..." },
    { "object_name": "profiles/def", "url": "http://..." },
    { "object_name": "profiles/ghi", "url": "http://..." },
    { "object_name": "profiles/jkl", "url": "http://..." }
  ]
}
```

**频控**: 30s
**校验**: prompt 含敏感词 → 422

一次调用生成 4 张候选图并全部存入 MinIO，`url` 为默认选中的第 1 张，`options` 为 4 张候选。用户选择后调用：

```
POST /shops/{shop_id}/profiles/{platform}/select-avatar
POST /shops/{shop_id}/profiles/{platform}/select-bg-image
```

**请求体**:
```json
{ "object_name": "profiles/abc" }
```

服务端校验 `object_name` 属于本次生成画廊后写入 `original_url`，返回 `200 ImageGenerateResponse`。

### POST /shops/{shop_id}/profiles/{platform}/generate-bg-image

豆包生成背景图（2K 宽幅）。请求/响应同上。

**original_url 规则**:
- 生成时 → 4 张候选写入 `avatar_gallery` / `bg_gallery`，第 1 张写入 `avatar_original_url` / `bg_original_url`（**覆盖**旧值）
- 用户选择候选后 → 选中图覆盖 `original_url`，同时清空 `url`（旧裁剪结果失效）
- 手动上传时 → 覆盖 `original_url` 并清空对应 gallery

---

## 4. 手动上传

### POST /shops/{shop_id}/profiles/{platform}/upload-avatar

**请求**: `multipart/form-data`，字段 `file`
- 允许 MIME: `image/png`, `image/jpeg`, `image/webp`
- 大小限制: <= 10MB

### POST /shops/{shop_id}/profiles/{platform}/upload-bg-image

同上。

**original_url 规则**: 上传时写入 `original_url`（覆盖），不清除 `url`。

---

## 5. 图片裁剪

### POST /shops/{shop_id}/profiles/{platform}/crop-avatar

**请求体**: `CropRequest`
```json
{ "image_base64": "iVBORw0KGgo..." }
```

- base64 解码后 <= 10MB
- 支持带 `data:image/png;base64,` 前缀

**响应**: `200 CropResponse`
```json
{ "url": "http://..." }
```

**裁剪基准**: 始终从 `original_url` 出发（前端裁剪器的图片来源必须是 original_url）

### POST /shops/{shop_id}/profiles/{platform}/crop-bg-image

同上。

**url 写入规则**: 裁剪结果覆盖 `avatar_url` / `bg_image_url`，不触碰 `original_url`。

---

## 6. 色板预设

### GET /color-schemes

无需认证。

**响应**: `200 list[ColorSchemePreset]`
```json
[
  {
    "name": "暖冬橘",
    "primary": "#E8793A",
    "secondary": "#FFF3EC",
    "accent": "#D4520A",
    "text": "#2D1A0A",
    "description": "火锅/中式正餐"
  }
]
```
共 8 组预设。

---

## 7. 错误码汇总

| 状态码 | 场景 |
|---|---|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 文件类型/大小不符、缺少原图 |
| 401 | 未认证 |
| 403 | 无权访问 |
| 404 | 资源不存在 |
| 409 | 乐观锁冲突 |
| 422 | 参数校验失败 |
| 429 | 频控触发 |
| 502 | 豆包/LLM 上游服务失败或鉴权失败 |

---

## 8. 豆包 API 接入参数（已核实）

已通过火山引擎 Ark `images/generations`（OpenAI 兼容）端点真实调用验证：

| 项目 | 确认值 | 说明 |
|---|---|---|
| API endpoint | `https://ark.cn-beijing.volces.com/api/v3/images/generations` | OpenAI 兼容 |
| 鉴权方式 | `Authorization: Bearer <API Key>` | API Key 从 `VOLCENGINE_API_KEY` 环境变量读取 |
| size | 头像 `2048x2048`；背景 `2K` | Seedream 5.0 最低面积约 3686400 像素，旧 1024x1024/1792x1024 不再可用 |
| response_format | `url` | 流式接口只返回 URL，后端下载后立即转存 MinIO |
| watermark | `false` | 关闭默认水印 |
| 锚点图 image | 单图字符串 `data:image/png;base64,...` | 后端统一转 PNG；单张 <=10MB，支持 jpeg/png/webp 上传；生成时提示词强制保留锚点图核心元素 |
| sequential_image_generation | `auto` + `max_images=4` | 提示词明确要求 4 张变体时一次返回 4 张 |
| 模型名 | `doubao-seedream-5-0-260128` | 与前端生图链路一致 |
| 响应字段 | SSE `image_generation.partial_succeeded` 的 `url` | URL 24 小时内有效，后端拿到后立即转存 MinIO |

**错误映射**: 豆包返回 400 时透传 400；401/403/5xx 映射为 502；429 提示稍后重试。

---

## 9. 字段语义表（供 P2/P3 引用）

| 字段 | 写入时机 | 覆盖策略 |
|---|---|---|
| avatar_original_url | 生成头像/上传头像 | **覆盖**旧值 |
| bg_original_url | 生成背景/上传背景 | **覆盖**旧值 |
| avatar_gallery | 生成头像 | 4 张候选**覆盖**；手动上传时清空 |
| bg_gallery | 生成背景 | 4 张候选**覆盖**；手动上传时清空 |
| avatar_url | 裁剪头像 | **覆盖**旧值，不触碰 original |
| bg_image_url | 裁剪背景 | **覆盖**旧值，不触碰 original |
| avatar_gen_prompt | 生成头像 | **覆盖**旧值；上传时**置 null** |
| bg_gen_prompt | 生成背景 | **覆盖**旧值；上传时**置 null** |
| ai_variants | POST /generate | **覆盖**旧值（历史方案丢弃） |

---

## 10. 契约漂移说明

P2/P3 联调第一步：用 Swagger (`/docs`) 反查本文档是否一致。不一致以真实接口为准，并**回写本文档**。

---

## 11. 新增端点：锚点生图 + 截图风格复刻

> P2.5 新增，路由前缀 `/api/v1`，鉴权与店铺所有权校验同前。

### 11.1 带锚点图生图

```
POST /shops/{shop_id}/profiles/{platform}/generate-avatar-with-ref
POST /shops/{shop_id}/profiles/{platform}/generate-bg-image-with-ref
```

**请求**: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| prompt | string | 是 | 生图提示词；含敏感词 → 422 |
| ref_image | file | 否 | 锚点图，<= 10MB；上传后生成结果必须保留锚点图核心主体、元素与配色 |

**响应**: `200`，同普通生图：

```json
{
  "url": "http://...",
  "prompt": "A round hot pot logo design...",
  "options": [
    { "object_name": "profiles/abc", "url": "http://..." },
    { "object_name": "profiles/def", "url": "http://..." },
    { "object_name": "profiles/ghi", "url": "http://..." },
    { "object_name": "profiles/jkl", "url": "http://..." }
  ]
}
```

**频控**: 与 `generate-avatar` / `generate-bg-image` 共用同一 30s 频控 key
**original_url 规则**: 4 张候选写入 gallery，第 1 张覆盖 `avatar_original_url` / `bg_original_url`，并清空旧裁剪 url；选择接口同普通生图。

### 11.2 截图风格复刻

```
POST /shops/{shop_id}/profiles/{platform}/analyze-style
```

**请求**: `multipart/form-data`，字段 `image`（<= 10MB）

**响应**: `200` JSON

```json
{
  "vibe": "日系清新",
  "dominant_colors": ["#E8C37A", "#FFFBF0", "#C49A3C", "#4A3A1A"],
  "nickname_style": "emoji+店名",
  "bio_style": "短句+emoji",
  "avatar_style": "logo",
  "bg_style": "门头照",
  "suggested_prompt": "A cozy bakery storefront, soft natural light"
}
```

**说明**: 分析失败兜底时仅返回 `vibe` / `dominant_colors` / `suggested_prompt`。
