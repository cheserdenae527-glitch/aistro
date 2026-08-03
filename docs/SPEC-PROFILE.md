# AiRestro — 平台账号装修模块 设计规约

> 版本：v0.2 · 2026-07-31
> 状态：定稿 · 自成一类模块
> 变更：v0.1 → v0.2 修复技术审查问题 + 接入火山引擎豆包生图

---

## 1. 模块定位

为服务商运营人员提供平台账号 Profile 页的全方位装修设计工具。
MVP 先做小红书，架构预留多平台扩展。
覆盖 **昵称、头像、背景图、简介** 四项装修元素 + **色系方案** 作为全局设计约束。
AI 一键生成多套方案，编辑器内实时预览，最终由运营人员手动复制粘贴到目标平台。

---

## 2. 小红书 Profile 页面结构（目标平台规格）

```
+------------------------------+
|        背景图 (Banner)        |  <- bg_image
+------------------------------+
|  +----+                      |
|  |头像|  昵称                  |  <- avatar + nickname
|  +----+  小红书号              |
|                               |
|  简介文案...                   |  <- bio
|  ---------                    |
|  获赞与收藏 | 关注 | 粉丝       |
+------------------------------+
```

平台规格约束：
- 头像：圆形裁剪，建议 >= 400x400px
- 背景图：横条，目标比例 1125:420（约 8:3）
- 昵称：最长 20 字符，**不可含表情符号**(后端校验：需使用 `regex` 第三方库（`pip install regex`），Python 标准库 `re` 不支持 `\p{}` Unicode 属性转义；或手动维护 emoji code point 区间)
- 简介：最长 100 字符，支持换行，**允许 emoji**（如 📍、✨、🔥 等排版用表情）

---

## 3. 编辑器布局

```
+---------- Left Panel (编辑) --------+---- Right Panel (实时预览) --+
|                                      |                              |
|  +-- 色系方案 ------------------+   |   +-- 平台模拟预览 --------+  |
|  |  [预设色板]  [自定义取色]     |   |   |                         |  |
|  |  ■ 暖冬橘 ■ 森系绿 ■ 莫兰迪  |   |   |  +-----------------+    |  |
|  |  ■ 日系奶油 ■ 高级灰 ■ 江湖红|   |   |  |   背景图         |    |  |
|  |  ■ 自定义...                 |   |   |  +-----------------+    |  |
|  |  主色 [■] #E74C3C           |   |   |  +--+                    |  |
|  |  辅色 [■] #FFF5F5           |   |   |  |头像| 昵称              |  |
|  |  点缀 [■] #C0392B           |   |   |  +--+ 简介文案...       |  |
|  |  文字 [■] #333333           |   |   |  ------------            |  |
|  +------------------------------+   |   |  0 获赞 · 0 粉丝 · 0 关注|  |
|                                      |   +-------------------------+  |
|  +-- AI 智能生成 --------------+   |                                  |
|  |  品类 [火锅           ▼]    |   |   左侧任何改动 -> 右侧实时刷新    |
|  |  风格 [市井烟火感    ]     |   |                                  |
|  |  价格 [人均80         ]     |   |                                  |
|  |  [⚡ 生成装修方案]          |   |                                  |
|  |  +----+----+----+----+    |   |                                  |
|  |  |方案A|方案B|方案C|方案D|   |   |                                  |
|  |  +----+----+----+----+    |   |                                  |
|  +------------------------------+   |                                  |
|                                      |                                  |
|  +-- 逐项微调 ------------------+   |                                  |
|  |  昵称 [蜀味·市井火锅] 8/20 │   |                                  |
|  |  候: [蜀味·市井火锅] [蜀味]  │   |  <- 方案自带 nickname_options   |
|  |       [蜀味老火锅(玉林店)]    │   |     点击候选填入输入框           |
|  |       [✨AI 写几个备选]      │   |  <- 独立的备选生成（结果也追加   |
|  |                               │   |     到候选列表）                |
|  |  简介 [_________] 67/100    │   |                                  |
|  |       (支持换行,允许emoji)   │   |                                  |
|  |       [✨AI 写几个备选]      │   |                                  |
|  |  头像 [选择文件] [🎨AI生图] │   |                                  |
|  |       [裁剪编辑]             │   |                                  |
|  |  背景 [选择文件] [🎨AI生图] │   |                                  |
|  |       [裁剪编辑]             │   |                                  |
|  +------------------------------+   |                                  |
|                                      |                                  |
|  [💾 保存草稿]  [📋 一键复制全部文案]│                                  |
+--------------------------------------+----------------------------------+
```

---

## 4. 数据模型

### shop_profiles

一条记录 = 一个门店在某个平台的装修快照。多平台各存一份，互不影响。
唯一约束：`(shop_id, platform)` 唯一索引，upsert 语义。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK -> shops | 关联门店 |
| platform | enum (v1: xiaohongshu) | 平台标识 |
| nickname | varchar(50) | 昵称，入库前过滤 emoji |
| bio | text | 简介，**允许** emoji |
| avatar_url | text | 头像图片 URL（裁剪后，MinIO） |
| avatar_original_url | text | 头像生成/上传后的原图 URL（未裁剪） |
| avatar_gen_prompt | text | 生成头像用的 prompt（可复现） |
| bg_image_url | text | 背景图 URL（裁剪后） |
| bg_original_url | text | 背景图生成/上传后的原图 URL（未裁剪） |
| bg_gen_prompt | text | 生成背景图用的 prompt |
| color_primary | varchar(7) | 主色 #RRGGBB |
| color_secondary | varchar(7) | 辅色 |
| color_accent | varchar(7) | 点缀色 |
| color_text | varchar(7) | 文字色 |
| color_mode | enum preset / custom | 色系来源（见 5 节规则） |
| color_preset_name | varchar(50) nullable | 预设名称，custom 时为 null |
| ai_input_category | varchar(50) | 生成时的品类 |
| ai_input_style | varchar(200) | 生成时的风格关键词 |
| ai_input_price | varchar(50) | 生成时的价格带 |
| ai_variants | jsonb | 最新一次 AI 生成的 4 套方案 |
| bio_flagged | boolean default false | bio 是否被敏感词过滤替换过 |`n| status | enum draft / published | |
| version | int | 乐观锁版本号，每次 PUT 自增 |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 字段约束汇总

| 字段 | 约束 |
|---|---|
| nickname | 最长 20 字符，**过滤 emoji**（`regex` 第三方库 `\p{Extended_Pictographic}`，标准库 `re` 不支持） |
| bio | 最长 100 字符，**允许 emoji** |
| avatar_original_url | 生成/上传时写入，**重新生成时覆盖** |
| bg_original_url | 生成/上传时写入，**重新生成时覆盖** |
| avatar_url / bg_image_url | 裁剪操作写入，可多次覆盖 |

### original_url 覆盖规则

| 操作 | avatar_original_url | avatar_url |
|---|---|---|
| AI 生成头像 | **覆盖**为新图 | 不变（等用户裁剪） |
| 手动上传头像 | **覆盖**为新图 | 不变 |
| 裁剪头像 | 不变 | **覆盖**为裁剪结果 |

### MinIO 孤儿文件（已知限制）

original_url 覆盖时旧文件不自动删除。用户每次重新生成头像/背景，MinIO 中旧的原图文件仍保留，会导致存储成本累积。MVP 阶段不做自动清理，后续可通过定时任务基于引用计数做垃圾回收。

### 裁剪基准

**裁剪始终从 `original_url` 出发**。即使用户裁剪两次，第二次裁剪的输入仍是原始大图（`original_url`），而非上一次裁剪结果。这样可以避免反复编码导致的画质劣化和裁剪区域基准漂移。前端裁剪器的图片来源始终是 `original_url`。

### 并发控制

PUT 保存草稿时客户端必须带 `version` 字段。服务端：
```python
if request.version != db.version:
    raise HTTPException(409, detail="数据已被他人修改，请刷新后重试")
db.version += 1
```

### ai_variants 覆盖策略

每次调用 POST `/generate` 都会**覆盖** `ai_variants` 字段。如果用户生成了第二轮的 4 套方案，第一轮的结果会丢失。
这是预期行为——"历史版本管理"在 MVP 不做。建议在生成前先保存草稿以保留上一轮数据。

### ai_variants JSON Schema


### variant 过滤标记

每个 variant 可含 `filtered: true` 字段，表示该 variant 在敏感词过滤后不再有效（如 nickname_options 全部被剔除、bio 整体被替换等）。前端渲染 VariantCards 时跳过 `filtered: true` 的方案。

`json
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
      "bio": "手工现炒底料 | 市井烟火气 | 人均80吃到撑\n📍成都·玉林路 每日11:00-24:00营业",
      "avatar_prompt": "A round hot pot logo design with red chili and Sichuan peppercorn elements, minimalist style, warm red background with white character inscription, professional food brand identity, clean vector style, square composition",
      "bg_prompt": "Warm-toned hot pot top view, red chili broth steam rising, fresh ingredients arranged around, rustic wooden table, soft warm lighting, cozy Shichiku atmosphere, food photography style, wide landscape composition"
    }
  ]
}
```

---

## 5. 预设色系方案

| 预设名 | 主色 | 辅色 | 点缀 | 文字 | 适用品类 |
|---|---|---|---|---|---|
| 暖冬橘 | #E8793A | #FFF3EC | #D4520A | #2D1A0A | 火锅/中式正餐 |
| 森系绿 | #4A8C5C | #F0F7F1 | #2D6A3F | #1A2D1F | 轻食/沙拉/素食 |
| 莫兰迪 | #9B8E8A | #F5F2F0 | #7A6E6A | #3A3330 | 甜品/咖啡 |
| 日系奶油 | #E8C37A | #FFFBF0 | #C49A3C | #4A3A1A | 烘焙/面包/Brunch |
| 高级灰 | #6B6B6B | #F7F7F7 | #4A4A4A | #1A1A1A | 高端餐饮/西餐 |
| 江湖红 | #C93828 | #FFF0EE | #A82015 | #2A0A08 | 川菜/湘菜/江湖菜 |
| 清凉蓝 | #5B8FB8 | #F0F6FA | #3D6D8E | #1A2A38 | 日料/海鲜 |
| 深夜紫 | #7B5EA7 | #F5F0FA | #5E3F89 | #201838 | 酒吧/居酒屋 |

### AI 生成色系规则

AI 生成色系时**优先从 8 个预设中选取匹配品类/风格的**。如果确实没有合适的预设，可以生成自定义色值：

| 情况 | color_mode | color_preset_name |
|---|---|---|
| AI 选了"江湖红" | preset | "江湖红" |
| AI 自创了不在预设中的颜色 | custom | null |
| AI 选了预设但微调了某个色值 | custom | null |

---

## 6. AI 生成流程

### 6.1 整体流水线

```
输入：品类 + 风格词 + 价格带
         |
         v
  +--------------------------+
  | LLM (GPT-4o)             |  <- 一次 API 调用
  | 输出：4 套完整方案       |     temperature=0.8
  | (昵称x3+简介+色系+       |
  |  avatar prompt + bg prompt)|
  +----------+---------------+
             |
    用户浏览 4 套方案 -> 选中一套 -> 表单填充
             |
   +---------+----------+
   v                    v
+----------+     +----------+
| 生头像   |     | 生背景   |  <- 火山引擎豆包 图片生成
| 1024x1024|     | 1792x1024|     size 参数控制
+----------+     +----------+
      |                |
      v                v
  原图存 MinIO（avatar_original_url / bg_original_url）
      |                |
      v                v
  用户可在编辑器中裁剪 -> base64 -> POST crop API
      |                |
      v                v
  裁剪后图片存 MinIO（avatar_url / bg_image_url）
```

### 6.2 生图规范（火山引擎豆包）

- **API 接入**：火山引擎豆包图片生成模型（如 doubao-seedream-4.0），通过 Ark SDK 或 HTTP API 调用
- **头像生成**：`size（豆包实际参数名和可选取值开工前核实文档，当前假设为 1:1 和 16:9 宽度比）`
- **背景图生成**：`size（豆包实际参数名和可选取值开工前核实文档，当前假设为宽幅比例）`
- 尺寸通过 API 参数传入，**不在 prompt 中拼任何尺寸语法**
- 生成后原图直接上传 MinIO，存为 `avatar_original_url` / `bg_original_url`

### 6.3 频控与重试

| 端点 | 频控 | 超时 | 重试策略 |
|---|---|---|---|
| POST /generate | 同 shop_id+platform 20秒内只能调用1次 | 30s | 失败返回 429/500，不自动重试 |
| POST /generate-avatar | 同 shop_id+platform 30秒内只能调用1次 | 60s | 失败返回错误，前端展示 retry 按钮 |
| POST /generate-bg-image | 同上 | 60s | 同上 |

频控基于 Redis（`rate_limit:{endpoint}:{shop_id}:{platform}`），TTL 过期后自动释放。

### 6.4 LLM Prompt 模板（生成 4 套方案）

```
你是一个平台账号装修设计师。为一家餐饮门店设计 4 套完整的 Profile 装修方案。

门店信息：
- 品类：{category}
- 风格关键词：{style}
- 人均价格：{price_range}

要求：
1. 4 套方案风格差异明显（暖调/冷调/高级感/亲和感）
2. 昵称 <= 20 字符（不允许 emoji），每套方案提供 3 个变体
3. 简介 <= 100 字符（允许 emoji 排版），真实有吸引力
4. 色系优先从下方预设中选取（匹配品类和风格）
   [8 色预设表]
   如果确实没有匹配预设，再自创。输出格式：{ primary, secondary, accent, text, preset_name|null }
5. avatar_prompt 用英文写图像生成提示词，描述适合该门店的头像 logo，方形构图
6. bg_prompt 用英文写图像生成提示词，描述符合该门店氛围的背景图，宽幅构图
   **不要在 prompt 中写入 --ar 参数或任何尺寸语法——尺寸由 API 参数控制**

输出严格的 JSON 格式：{ "variants": [...] }
```

### 6.5 图片裁剪流程

```
图片生成/上传
      |
      v
  原图存入 MinIO
  (avatar_original_url / bg_original_url)
      |
      v
  编辑器中展示原图
  用户点击 [裁剪编辑]
      |
      v
  前端 Canvas 裁剪器（图片来源始终是 original_url，保证二次裁剪不劣化）
  - 头像：圆形区域选取，1:1
  - 背景：矩形区域选取，1125:420 蒙版引导
      |
      v
  Canvas 导出 base64
      |
      v
  POST /crop API (JSON body: { image_base64 })
  -> 后端解码 -> 校验 -> 存 MinIO -> 返回 URL
  -> 写入 avatar_url / bg_image_url（覆盖旧裁剪结果）
```

裁剪始终从 `original_url` 出发，用户可多次裁剪覆盖 `avatar_url`。

---

## 7. API

路由参数化：`/shops/{shop_id}/profiles/{platform}`，当前 `platform=xiaohongshu`。

**全局鉴权**：所有接口均需 JWT 认证。`shop_id` 对应的门店必须属于当前登录用户（通过 merchant -> user 链校验），否则返回 403 Forbidden。

### 7.1 装修数据

```
GET    /api/v1/shops/{shop_id}/profiles/{platform}
  -> 返回当前装修数据（含 url、original_url、色系、version、bio_flagged 等标记字段）

PUT    /api/v1/shops/{shop_id}/profiles/{platform}
  -> Body: { nickname, bio, color_*, ..., version }
  -> 乐观锁校验 version
  -> 校验：nickname 过滤 emoji、bio 不过滤 emoji、字符数限制
  -> 409 Conflict 如果版本不匹配
```

### 7.2 AI 方案生成

```
POST   /api/v1/shops/{shop_id}/profiles/{platform}/generate
  -> Body: { category, style_keywords, price_range }
  -> 频控：同 shop_id+platform 20秒1次，超频返回 429
  -> 鉴权：shop_id 必须属于当前用户
  -> LLM 生成 4 套方案 -> 覆盖写入 ai_variants
  -> 返回 4 套方案（不含图片，图片单独生成）
```

### 7.3 图片生成（火山引擎豆包）

```
POST   /api/v1/shops/{shop_id}/profiles/{platform}/generate-avatar
  -> Body: { prompt }
  -> 频控：30秒1次
  -> prompt 敏感词过滤
  -> 调用火山引擎豆包图片 API (size（豆包实际参数名和可选取值开工前核实文档，当前假设为 1:1 和 16:9 宽度比）)
  -> 原图上传 MinIO -> 覆盖 avatar_original_url + avatar_gen_prompt
  -> 返回 { avatar_original_url }

POST   /api/v1/shops/{shop_id}/profiles/{platform}/generate-bg-image
  -> Body: { prompt }
  -> 频控：30秒1次
  -> prompt 敏感词过滤
  -> 调用火山引擎豆包图片 API (size（豆包实际参数名和可选取值开工前核实文档，当前假设为宽幅比例）)
  -> 原图上传 MinIO -> 覆盖 bg_original_url + bg_gen_prompt
  -> 返回 { bg_original_url }
```

### 7.4 图片上传（手动）

```
POST   /api/v1/shops/{shop_id}/profiles/{platform}/upload-avatar
  -> FormData: file
  -> 校验：MIME (image/png, image/jpeg, image/webp)，大小 <= 10MB
  -> 上传原图到 MinIO -> 覆盖 avatar_original_url -> 返回 { avatar_original_url }

POST   /api/v1/shops/{shop_id}/profiles/{platform}/upload-bg-image
  -> FormData: file
  -> 校验：MIME (image/png, image/jpeg, image/webp)，大小 <= 20MB
  -> 上传原图到 MinIO -> 覆盖 bg_original_url -> 返回 { bg_original_url }
```

### 7.5 裁剪结果上传

```
POST   /api/v1/shops/{shop_id}/profiles/{platform}/crop-avatar
  -> Body: { image_base64: string }
  -> ⚠️ 解码后图片大小 <=10MB（防 DoS）
  -> 解码 base64 -> 校验图片类型/尺寸 -> 存 MinIO
  -> 覆盖 avatar_url -> 返回 { avatar_url }

POST   /api/v1/shops/{shop_id}/profiles/{platform}/crop-bg-image
  -> Body: { image_base64: string }
  -> ⚠️ 解码后图片大小 <=10MB（防 DoS）
  -> 解码 base64 -> 校验图片类型/尺寸 -> 存 MinIO
  -> 覆盖 bg_image_url -> 返回 { bg_image_url }
```

### 7.6 颜色预设

```
GET    /api/v1/presets/color-schemes
  -> 返回 8 个预设色系列表
```

### 7.7 安全约束汇总

| 接口 | 约束 |
|---|---|
| 全部 | JWT 鉴权；shop_id 所有权校验（非当前用户的店铺返回 403） |
| PUT profile | nickname 过滤 emoji（`regex` 库），bio 不过滤；version 乐观锁；**nickname/bio 敏感词过滤** |
| upload-avatar | MIME: image/png, image/jpeg, image/webp; max 10MB |
| upload-bg-image | MIME: image/png, image/jpeg, image/webp; max 20MB |
| generate (LLM) | 频控: 20s/次；**输出 nickname_options/bio 经敏感词过滤后返回** |
| generate-avatar/bg | 频控: 30s/次; prompt 敏感词黑名单；超时 60s |


### 7.8 敏感词过滤范围（全文适用）

敏感词过滤不是只覆盖图片 prompt。以下位置同样做黑名单校验：

| 位置 | 过滤时机 | 违规处理 |
|---|---|---|
| generate-avatar prompt | 入参校验 | 400 Bad Request |
| generate-bg-image prompt | 入参校验 | 400 Bad Request |
| generate 输出的 nickname_options | LLM 返回后入库前 | 剔除违规候选项；若剔除后该 variant 的 nickname_options 为空，该 variant 整体标记 filtered:true（从返回的 4 套中过滤掉，不展示）；ai_variants 中保留但标记 filtered:true |
| generate 输出的 bio | LLM 返回后入库前 | 替换为 "[内容待审核]"；响应中标记 `bio_flagged: true`，前端据此在预览区高亮提示"该文案已被过滤，请重新生成或手动修改" |
| PUT profile 的 nickname | 入参校验 | 400 Bad Request |
| PUT profile 的 bio | 入参校验 | 400 Bad Request |

黑名单覆盖大类：色情、暴力、涉政、诈骗、赌博。同一套黑名单函数在所有上述位置复用。

**注意**：黑名单是第一道防线，LLM 自身的内容安全机制是第二道防线。黑名单不能替代 LLM safety filter，但能拦截 90%+ 的明显违规输入和偶发的不当输出。

---

## 8. 前端组件树

```
ProfileEditorPage (路由 /shops/:shop_id/profile/:platform)
+- LeftPanel
|   +- ColorSchemePanel
|   |   +- PresetColorGrid（8 个色板卡片，点击填充四色 + 设 color_mode=preset）
|   |   +- CustomColorPickers（4 个 ColorPicker，任意取色后 color_mode=custom）
|   +- AIGeneratePanel
|   |   +- CategorySelect, StyleInput, PriceInput
|   |   +- GenerateBtn（点击调用 POST /generate，处理 429 频控提示）
|   |   +- VariantCards（4 张方案卡片，点击应用）
|   |       +- 应用时：填充昵称/简介/色系/nickname_options + avatar/bg prompt
|   +- NicknameEditor
|   |   +- TextInput + 字数计数器
|   |   +- CandidateChips（方案自带的 nickname_options，点击填入）
|   |   +- AISuggestBtn（独立 LLM 生成备选，追加到 CandidateChips）
|   +- BioEditor
|   |   +- TextArea + 字数计数器 + 换行
|   |   +- AISuggestBtn（独立 LLM 生成备选简介）
|   +- AvatarEditor
|   |   +- UploadBtn (-> POST /upload-avatar)
|   |   +- AIGenerateBtn (-> POST /generate-avatar，可编辑 prompt)
|   |   +- PromptInput（可编辑的 prompt，默认填 variant 的 avatar_prompt）
|   |   +- CropBtn（打开 ImageCropper，圆形蒙版，来源图始终用 original_url）
|   +- BgImageEditor
|   |   +- 同 AvatarEditor 结构，宽幅蒙版
|   +- ActionBar
|       +- SaveDraftBtn（PUT /profiles，带 version，409 提示刷新）
|       +- CopyAllBtn（复制 昵称+简介 到剪贴板）
+- RightPanel
    +- PlatformPreview（按 platform 切换渲染）
        +- BgImageLayer, AvatarCircle, NicknameText, BioText
```

---

## 9. 编辑器交互流程

```
进入页面 -> GET profile 数据
  +- 有草稿 -> 加载草稿到编辑器 + 预览
  +- 无草稿 -> 空白编辑器 + 默认预览
       |
+------+------+
| 方式一：AI   |           | 方式二：手动  |
| 输入品类+风格 |           | 选色系/取色    |
| [生成] -> 4套 |           | 填昵称/简介   |
| 浏览方案卡片  |           | 上传或生成图片  |
| 点选方案      |           |               |
|   -> 表单填充 |           |               |
+------+------+           +------+--------+
       |                          |
       +------- 微调 --------------+
        - nickname chips 选一个或手动改
        - 改简介
        - 点 AI 生图（豆包）或手动上传
        - 裁剪头像/背景（始终从 original 出发）
        - 改色系
                          |
        [💾 保存草稿]（version 校验，429=频控, 409=冲突）
                          |
              实时预览同步
                          |
        [📋 复制文案] -> 剪贴板
                          |
              运营去平台手动粘贴
```

---

## 10. 技术实现要点

### 10.1 实时预览
- 编辑器 state 变更 -> React 受控组件 -> 预览区即时渲染
- 配色改变 -> 预览区 CSS 变量注入

### 10.2 AI 方案生成
- 单次 LLM 调用返回 4 套方案；Pydantic 严格校验 JSON

### 10.3 图片生成（火山引擎豆包）
- 接入方式：火山引擎 Ark SDK 或 HTTP API
- `size` 参数控制尺寸（非 prompt 语法）
- 原图立即存 MinIO，预览用原图；裁剪图覆盖 avatar_url/bg_image_url

### 10.4 图片裁剪
- 前端 Canvas API，**来源始终用 original_url**（保证二次裁剪不劣化）
- 头像：圆形选取，1:1；背景：矩形选取，1125:420 蒙版

### 10.5 乐观锁
- PUT 必须带 version；后端 CAS 更新；409 提示刷新

### 10.6 Emoji 过滤
- **仅 nickname** 做 emoji 过滤（`regex` 第三方库，非标准库 `re`）
- **bio 不过滤**，允许 emoji 排版

### 10.7 鉴权
- 所有 API 校验 JWT + shop 所有权（shop -> merchant -> user 链）

---


### 10.7b CopyAllBtn 安全拦截

`bio_flagged=true` 时，CopyAllBtn 必须弹二次确认对话框（"简介未通过内容审核，是否仍要复制？"），不能直接复制。这是该功能中唯一将内容直接暴露到公网的出口，高亮提示不够，需要硬拦截。

### 10.8 测试最低要求（P1 交付物的一部分）

以下逻辑必须有自动化测试覆盖（pytest）：

| 测试场景 | 验证点 |
|---|---|
| 乐观锁并发更新 | 两个请求带相同 version，第二个返回 409 |
| 频控触发 | 连续两次 generate 调用，第二次返回 429 |
| original_url 覆盖 | 生成头像后 original_url 写入，裁剪后 avatar_url 写入但 original_url 不变 |
| 重新生成覆盖 original | 第二次生成头像后 original_url 更新为新图 URL |
| 敏感词过滤 - prompt | 含黑名单关键词的 prompt 返回 400 |
| 敏感词过滤 - nickname | 含黑名单关键词的 nickname 返回 400 |

---

## 11. 路由

| 路由 | 页面 |
|---|---|
| /shops/:shop_id/profile/:platform | 平台账号装修编辑器 |

参数化 `:platform`，当前值为 `xiaohongshu`。

---

## 12. MVP 边界

### 包含
- 8 套预设色系 + 自由取色
- AI 一键生成 4 套完整方案（昵称候选/简介/色系/prompt）
- 选中方案后 nickname chips 展示 + 填入
- 火山引擎豆包 图片生成（头像+背景，size 参数控制尺寸）
- 手动上传头像+背景（类型/大小校验）
- 图片裁剪（圆形头像 + 宽幅背景，始终从 original 出发）
- 原图保留（original_url 独立字段，重新生成时覆盖）
- 昵称 emoji 过滤（仅 nickname，bio 允许 emoji）
- 乐观锁并发（version 字段）
- 频控（generate 60s，生图 30s）
- 多租户鉴权（JWT + shop 所有权）
- 实时预览 + 保存草稿 + 一键复制

### 不包含
- 直接发布到小红书 API
- 抖音/美团等其他平台装修
- 历史版本管理
- A/B 测试装修效果
- 多套方案同时保存









