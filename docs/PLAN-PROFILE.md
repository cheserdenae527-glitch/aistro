# 平台账号装修模块 — 实现计划

> 基于 SPEC-PROFILE v0.2 · 独立于主项目里程碑

## 依赖与前置检查

| 依赖 | 状态 | 备注 |
|---|---|---|
| shops 表 + 门店详情页 | 需确认 | M2 产物 |
| MinIO 对象存储 | 需确认 | 图片上传基础设施 |
| AI Service 抽象层（LLM） | 需确认 | GPT-4o 调用封装 |
| 火山引擎豆包 API（图片生成） | 需 P1 接入 | Ark SDK 或 HTTP API |
| JWT 鉴权中间件 | 需确认 | FastAPI deps 中应有 get_current_user |
| Redis | 需确认 | 频控依赖 |
| `regex` 三方库 | P1 安装 | `pip install regex`，Python 标准库 `re` 不支持 `\p{}` Unicode 属性转义 |

---

## P1 — 后端数据模型 + API + AI Service

**目标**：shop_profiles 表 + 全部 API + AI 生成链路 + 豆包生图集成

```
工作量：1 次对话（优先策略见下）
```

### 任务清单

1. **Alembic 迁移**：shop_profiles 表
   - 含 version 字段、avatar_original_url/bg_original_url
   - (shop_id, platform) 唯一约束

2. **SQLAlchemy 模型**：ShopProfile
   - 乐观锁 update 方法（version 比对 + 自增）

3. **Pydantic Schema**
   - 请求/响应校验
   - nickname 过滤 emoji：**使用 `regex` 第三方库**，非标准库 `re`
   - bio **不过滤** emoji
   - 字数限制

4. **鉴权校验**（嵌入所有写操作）
   - `shop_id` 所有权校验：shop -> merchant.user_id == current_user.id
   - 非所有者返回 403

5. **API 实现**：
   - GET/PUT profile CRUD（version 校验，409 Conflict）
   - POST generate（频控 20s，超频 429）
   - POST generate-avatar / generate-bg-image（频控 30s，豆包 API）
   - POST upload-avatar / upload-bg-image（FormData，MIME+大小校验）
   - POST crop-avatar / crop-bg-image（JSON body base64，⚠️ **解码后 <=10MB**）
   - GET color-schemes（8 个预设）

6. **AI Service：Profile AI Agent**
   - LLM prompt（含 8 预设色板表，JSON 输出校验）
   - Pydantic 解析 variants JSON

7. **图片生成 Service：火山引擎豆包**
   - **⚠️ 先核实豆包 API 文档**：参数名是否叫 `size`、支持的尺寸枚举值、鉴权方式（SDK vs REST）、响应字段名
   - 核实后封装调用
   - 生成后上传 MinIO -> 回写 original_url

8. **频控中间件**
   - Redis 实现：key = `rate_limit:{endpoint}:{shop_id}:{platform}`
   - generate: 20s TTL，生图: 30s TTL

9. **字段语义落地**：
   - original_url：生成/上传时**覆盖**
   - avatar_url/bg_image_url：裁剪时**覆盖**
   - 裁剪基准：始终从 original_url 发起

10. **自动化测试**（交付物的一部分）：
    - 乐观锁并发更新 -> 409
    - 频控触发 -> 429
    - original_url 覆盖规则验证
    - 敏感词过滤（prompt/nickname/bio 各一条）

### 优先策略

```
P0（必须完成）：1-5 + 敏感词过滤（全文）+ 鉴权
P1（尽力完成）：6-7（AI Service + 豆包生图 Service）
P2（可推到 P1.5）：8-9（频控 + 字段语义文档）
```

### 敏感词过滤（P0，全文适用）

**覆盖范围**（不仅仅是图片 prompt）：

| 位置 | 时机 | 违规处理 |
|---|---|---|
| generate-avatar prompt | 入参校验 | 400 |
| generate-bg-image prompt | 入参校验 | 400 |
| generate 输出的 nickname_options | LLM 返回后入库前 | 剔除违规项；剔除后为空则该 variant 标记 filtered:true，前端不展示 |
| generate 输出的 bio | LLM 返回后入库前 | 替换为 "[内容待审核]"；API 响应标记 bio_flagged:true，前端高亮提示 |
| PUT profile nickname | 入参校验 | 400 |
| PUT profile bio | 入参校验 | 400 |

同一套黑名单函数在所有位置复用。黑名单覆盖：色情、暴力、涉政、诈骗、赌博。

**⚠️ 这是合规底线**：文本内容（昵称/简介）一旦保存并发到小红书公开页面，没有平台侧二次拦截，风险不低于图片生成。

### 交付物
- Swagger 可调用所有 API
- GET/PUT profile 响应包含 bio_flagged 标记字段
- generate 接口过滤后若 variant 无效则标记 filtered:true
- 豆包图片生成接口已验证参数名和尺寸枚举
- **接口契约文档**（供 P2/P3 引用）:
  ```
  docs/contracts/profile-api.md
  ```
  包含：所有端点路径、字段名+类型、错误码、nickname_options key 名、ai_variants JSON 结构、version 校验规则、original_url 覆盖规则、豆包 API 参数详情
- **⚠️ 契约漂移说明**：P2 联调时第一步用 Swagger 反查契约文档是否一致，不一致以真实接口为准并回写文档
- **6 条自动化测试**通过（pytest）

---

## P2 — 前端装修编辑器

**目标**：完整的装修编辑器 + 实时预览 + 对 P1 真实 API 联调

```
前置：P1（需 P1 的接口契约文档 + 真实 API 可用）
工作量：1 次对话
```

### 任务清单

1. 路由注册：/shops/:shop_id/profile/:platform
2. 侧边栏菜单添加入口
3. 页面布局：左右分栏
4. ColorSchemePanel（预设色板 + 自定义 ColorPicker，color_mode 切换）
5. AIGeneratePanel
   - 429 提示：倒计时 + "调整品类/风格关键词后重试"
   - 跳过 filtered:true 的 variant，不展示其卡片
   - 如 4 套全部被过滤，提示"当前方案均未通过内容审核，请调整关键词后重试"
   - 选中方案后：nickname chips + 色系 + prompt 填入生图区
6. NicknameEditor（输入框 + 字数计数 + candidate chips + AI 建议按钮）
7. BioEditor（TextArea + 字数计数 + AI 建议按钮）
8. AvatarEditor / BgImageEditor（上传 + 豆包生图 + prompt 编辑 + 裁剪按钮）
9. PlatformPreview（按 platform 切换预览）
10. ActionBar
    - SaveDraftBtn：PUT /profiles（version，409 刷新提示）
    - **CopyAllBtn：bio_flagged=true 时弹二次确认（"简介未通过内容审核，是否仍要复制？"），确认后才复制；bio_flagged=false 直接复制**
11. 实时同步（编辑器 state -> 预览）
12. **真实 API 联调**：
    - 第一步：Swagger 反查契约文档是否一致，不一致回写
    - 对接 P1 全部接口

### 交付物
- 页面完整可用，所有 API 真实联调通过
- 429/409 提示 + 倒计时
- CopyAllBtn 二次确认拦截可用（bio_flagged=true 场景）
- 契约文档已同步

---

## P3 — 生图集成 + 图片裁剪

**目标**：生图、上传、裁剪全链路 + original_url 语义验证

```
前置：P1 + P2
工作量：1 次对话
```

### 任务清单

1. 前端 Canvas 裁剪器（圆形 + 宽幅蒙版）
2. 裁剪后 base64 -> POST /crop API（⚠️ 大小 <=10MB）
3. 豆包生图联调（参数名+尺寸已核实）
4. 手动上传联调（MIME/大小校验）
5. original_url 语义验证：
   - 生成/上传 -> original_url 写入，裁剪 -> avatar_url 写入
   - 重新生成 -> original_url 被覆盖
   - 两次裁剪：第二次仍从 original_url 出发
6. 生图/上传 loading + 取消 + 错误提示
7. 频控交互联调（429 + 倒计时）

### 交付物
- 豆包生图 -> 裁剪 -> 预览全链路通过
- 两次裁剪基准为 original_url
- 频控正常

### 已知限制
- MinIO 旧原图不自动删除（孤儿文件），后续加定时 GC

---

## 执行顺序

```
P1 (后端+AI+豆包) -> P2 (前端编辑器) -> P3 (生图+裁剪集成)
```

每个阶段开独立对话。P2/P3 引用 `docs/contracts/profile-api.md` 作为接口基线。



