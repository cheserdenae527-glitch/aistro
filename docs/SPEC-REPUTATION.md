# AiRestro — 口碑管理板块 设计规约

> 版本：v0.1 · 2026-08-03
> 状态：定稿 · 自成一类模块

---

## 1. 模块定位

独立入口（侧边栏"口碑管理"）。面向代运营团队，把各平台对门店的口碑内容聚合、分析、处理。

MVP 先做小红书，架构按多平台设计（大众点评/美团/抖音后补）。

---

## 2. 小红书口碑模型

小红书没有统一评分体系，口碑由两部分构成：

| 类型 | 定义 | 用途 |
|---|---|---|
| **笔记** | 提到门店的探店/吐槽帖子（作者、标题、正文、赞藏评互动） | 只做口碑分析（情感/关键词/互动量），**不生成回复草稿** |
| **评论** | 笔记评论区里的互动 | 生成 AI 回复草稿，人工确认后复制到小红书粘贴 |

后续大众点评/美团接入时才有 `rating`（1-5 分），数据模型需兼容"无评分"和"1-5 分"两种形态。

---

## 3. 数据模型（扩展现有 reviews 表）

在现有 `reviews` 表基础上新增字段，保留 `rating / content / tags / sentiment / reply_status / ai_reply / reply_content / replied_at / reviewed_at`。

### 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| review_type | enum note / comment / rating_review | 内容类型，默认 rating_review（美团/点评） |
| parent_review_id | UUID FK → reviews nullable | 评论挂到所属笔记 |
| note_title | varchar(200) nullable | 笔记标题 |
| note_url | text nullable | 笔记链接（xsec_token 记录在内） |
| author_id | varchar(100) nullable | 平台作者 ID |
| author_avatar | text nullable | 作者头像 |
| interact_stats | jsonb nullable | 笔记互动：liked/collected/comments/shared |
| source_json | jsonb nullable | 爬虫原始数据，回看/排障用 |
| alert_status | enum none / triggered / acknowledged | 差评预警状态，默认 none |
| alert_reason | jsonb nullable | 预警触发原因（见 5.3 节） |

### 去重约束

`(platform_shop_id, review_type, platform_review_id)` 唯一索引：
- 笔记：`platform_review_id = 笔记 ID`
- 评论：`platform_review_id = 评论 ID`
- 重复同步直接跳过，不产生重复记录

**迁移注意事项（R1 必须先做数据体检）**：现有 reviews 表可能已有大众点评/美团历史数据且无 `review_type`。添加字段和唯一索引前：
1. 历史数据统一回填 `review_type=rating_review`
2. 检查 `(platform_shop_id, platform_review_id)` 是否存在重复/空值冲突
3. 存在冲突时先清理或报告，再建唯一索引

### 字段语义

| 内容类型 | rating | reply_status | 回复对象 |
|---|---|---|---|
| note | NULL | NULL（reply_status 改为 nullable；笔记不参与回复筛选） | 无 |
| comment | NULL | unreplied / ai_replied / manual_replied | 可生成回复草稿 |
| rating_review | 1-5 | 同上 | 后续平台 |

---

## 4. AI 能力

### 4.1 批量情感 + 关键词分析

`POST /reviews/batch-analyze`：
- 请求最多 **20 条** review id
- 后端自动分批（每批 ≤10 条）调用 DeepSeek，避免单次输出过大
- 返回每条：`sentiment(positive/neutral/negative)` + `tags[]`
- 写入 `reviews.sentiment` / `reviews.tags`
- **batch-analyze 只做情感分析，不重复关键词扫描**：关键词路径已在同步落库时覆盖（见 5.1），避免实现者误以为该接口还要再跑一次关键词判断

**部分失败语义**：某一批 LLM 调用失败（超时/限流）不影响其他批次。响应结构：
```json
{
  "analyzed": [{ "id": "uuid", "sentiment": "negative", "tags": ["分量少"] }],
  "failed": ["uuid1", "uuid2"],
  "total": 20,
  "success_count": 18,
  "failed_count": 2
}
```
前端对 `failed` 列表提供"重试分析"按钮，不整体失败。

### 4.2 评论回复草稿

`POST /reviews/{rid}/ai-reply`：
- **仅 review_type=comment 可用**，note 返回 400
- 输入：评论内容 + 门店信息（店名/品类/定位）
- 输出：1 条回复草稿（好评：感谢+引导复购；差评：道歉+解释+补偿方案）
- 草稿写入 `ai_reply`，`reply_status = ai_replied`
- 生成后过敏感词过滤，命中则返回错误提示"重新生成"

**校验顺序**：敏感词校验先于频控。命中敏感词返回 422 时**不占用 20s 频控窗口**，运营可以立即修改重试；只有进入 LLM 调用的成功路径才设置频控 key。

### 4.3 交付方式

草稿 → 前端编辑 → 运营复制 → 到小红书粘贴 → 回系统标记 `manual_replied`。**不自动发布**（合规零风险，与装修板块一致）。

---

## 5. 差评预警

### 5.1 触发时机（双路径，不依赖人工分析）

预警有两条独立触发路径，**关键词扫描在同步落库时就执行**，不依赖运营手动分析：

| 触发路径 | 时机 | 条件 |
|---|---|---|
| 关键词命中 | 同步落库（sync / sync-comments）时 | 内容命中内置关键词：口味/分量/配送/包装/服务/等位/价格/卫生 等，无需 LLM |
| 负面情感 | batch-analyze 写入 sentiment 后 | `sentiment = negative` |

任一路径满足即触发，`alert_status = triggered`。运营不点批量分析，差评关键词预警也会在同步后立即生效。

### 5.2 状态机（ack 优先，不自动回跳）

```
none ──触发──→ triggered ──ack──→ acknowledged
                 │                    ▲
                 │                    │
                 └──manual_replied────┘
```

规则：
1. `ack` 后 `acknowledged` **永不自动重置**：即使之后重新 batch-analyze 且 sentiment 仍为 negative，也不回跳 `triggered`（避免"已处理又冒出来"）
2. `manual_replied` 时，若 `alert_status=triggered`，自动流转为 `acknowledged`（已回复即视为已处理）
3. `ack` 只允许 `triggered → acknowledged`：对 `alert_status=none` 的记录调用 ack 返回 400（防止从未触发的记录被提前锁死，导致后续真正触发被"不回跳"规则吞掉）；已 `acknowledged` 重复调用返回 200（幂等）
4. 内容更新只影响新增记录；既有记录的预警状态不被旧内容重算覆盖
5. **状态机只升不降**：`triggered` 一旦触发，不因重新分析变为 positive/neutral 而撤销回 `none`（哪怕当初纯 sentiment 触发、无关键词命中）。
6. **alert_reason 是"触发时快照"，不随后续重新分析更新**（方案 B）：
   - 触发时一次性写入 `type / keywords / sentiment`
   - 未 ack 时若发现新触发路径（如关键词先命中、随后分析为 negative），可合并升级 `type=both`（补充触发信息，仍属触发快照语义）
   - ack 后完全锁定，任何情况不再更新
   - 重新分析（无论判为 positive 还是 negative）不更新 alert_reason 内的 sentiment/type
   - `reviews.sentiment` 字段单独反映最新一次分析值，供列表标签/筛选使用
   - 前端展示：情感标签用 `reviews.sentiment`（最新），预警原因用 `alert_reason`（触发快照），两者独立展示，避免"type=both 但当前情感 positive"的矛盾

**alert_reason 的先后命中合并规则**：
- 同步落库先命中关键词 → `alert_reason={type:"keyword", keywords:[...], sentiment:null}`
- 之后 batch-analyze 判为 negative：
  - 若 `alert_status != acknowledged`：合并更新为 `{type:"both", keywords:[...], sentiment:"negative"}`
  - 若 `alert_status = acknowledged`：**不更新 alert_reason**（已处理记录锁定，即使状态不回跳，原因也不再追溯改写）
- 若 batch-analyze 先触发（sentiment 路径），后续关键词扫描不会再次运行（关键词只在同步时扫），不存在反向合并
- 重新分析判为 positive/neutral：只更新 `reviews.sentiment`，alert_reason 保持触发时快照不变

### 5.3 alert_reason 结构

`alert_reason` 持久化触发原因，`GET /alerts` 直接返回，不靠运行时反查：

```json
{
  "type": "keyword",
  "keywords": ["卫生", "分量少"],
  "sentiment": null
}
```

```json
{
  "type": "sentiment",
  "keywords": [],
  "sentiment": "negative"
}
```

两条路径同时命中时 `type` 取 `both`，两个字段都填。

### 处理

`POST /reviews/alerts/{rid}/ack` → `alert_status = acknowledged`，幂等（见 5.2 状态机）。

---

## 6. 爬虫采集流程

复用现有 XHS 爬虫（`XhsCrawler.search_notes` / `get_comments`）和 `processor.normalize_note / normalize_comment`。

```
POST /api/v1/shops/{shop_id}/reviews/sync/xiaohongshu
  Body: { keyword, limit ≤ 50（默认 20） }
  → search_notes(keyword, limit)
  → 笔记去重落库（review_type=note, rating=NULL）
  → 落库时同步执行关键词扫描（见 5.1），命中即触发预警
  → 返回新增/跳过数量

POST /api/v1/shops/{shop_id}/reviews/{rid}/sync-comments
  → 读取笔记的 note_url + xsec_token
  → get_comments(url)
  → 评论去重落库（review_type=comment, parent_review_id=笔记 id）
  → 落库时同步执行关键词扫描
```

**依赖与错误区分**：
- XHS cookie 有效；失效返回 502，detail 提示"登录态失效，请更新 cookie"
- `xsec_token` 有时效性：笔记同步后几天再拉评论可能过期。爬虫返回中需区分：
  - cookie 失效 → "登录态失效，请更新 cookie"
  - token 过期 → "笔记链接已过期，请重新同步该笔记"
- 无法区分时至少把两类错误原文带上，不吞没细节

---

## 7. API

全部 JWT 鉴权 + shop 所有权校验（shop → merchant → user），非所有者 404。

```
GET   /api/v1/shops/{shop_id}/reviews
  → 筛选：review_type / sentiment / reply_status / alert_status / keyword / date_from / date_to
  → alert_status 筛选是补充入口；预警主入口仍是独立 Tab
  → 分页：page / size

POST  /api/v1/shops/{shop_id}/reviews/sync/xiaohongshu
  → Body: { keyword, limit ≤ 50 }
  → 频控 60s，key = rate_limit:sync_notes:{user_id}:{shop_id}

POST  /api/v1/shops/{shop_id}/reviews/{rid}/sync-comments
  → 频控 60s，key = rate_limit:sync_comments:{user_id}:{shop_id}:{note_id}
  → 与 sync 使用独立 key，且不同笔记各自独立窗口：同一运营可连续展开多条不同笔记的评论区

POST  /api/v1/shops/{shop_id}/reviews/batch-analyze
  → Body: { review_ids: [最多20] }，超过 20 返回 400
  → 频控 30s，key = rate_limit:batch_analyze:{user_id}:{shop_id}
  → 响应：{ analyzed[], failed[], total, success_count, failed_count }

POST  /api/v1/shops/{shop_id}/reviews/{rid}/ai-reply
  → 仅 comment；敏感词 422 不占用频控；LLM 成功路径才设置 20s 频控 key

PUT   /api/v1/shops/{shop_id}/reviews/{rid}/reply
  → Body: { reply_content }
  → review_type=note 返回 400（笔记不参与回复）
  → 写入 reply_content，reply_status=manual_replied，replied_at=now
  → 已 manual_replied 的记录允许重复调用（覆盖 reply_content + 更新 replied_at，用于修改错别字/补充内容），前端不置灰
  → 若 alert_status=triggered，自动流转 acknowledged

GET   /api/v1/shops/{shop_id}/reviews/alerts
  → 返回 alert_status=triggered 列表（含 alert_reason 触发原因）

POST  /api/v1/shops/{shop_id}/reviews/alerts/{rid}/ack
  → 仅 triggered → acknowledged；none 返回 400；已 acknowledged 幂等 200

GET   /api/v1/shops/{shop_id}/reviews/summary
  → 概览：笔记数/评论数/情感分布/未回复数/预警数
  → "未回复数"只统计 review_type=comment 且 reply_status='unreplied'
  → 不使用 reply_status != 'manual_replied' 写法（NULL 语义会误伤/漏掉笔记）
```

**频控粒度**：所有频控 key 均为 `rate_limit:{endpoint}:{user_id}:{shop_id}`。同一门店的不同运营各自独立窗口，互不占用；同一运营连续操作才受限。

---

## 8. 前端页面

```
侧边栏"口碑管理"
  ├─ ReputationIndexPage（/reputation）
  │   └─ 门店选择列表
  └─ ReputationWorkbenchPage（/reputation/:shop_id）
      ├─ SummaryCards（笔记数 / 评论数 / 情感分布 / 未回复 / 预警数）
      ├─ Tab 评价列表
      │   ├─ FilterBar（类型 / 情感 / 回复状态 / 关键词 / 时间）
      │   ├─ NoteCard（笔记：标题+正文+互动+评论数，点击展开评论区）
      │   ├─ CommentRow（评论：作者+内容+情感标签+回复状态）
      │   ├─ BatchAnalyzeBar（勾选 ≤20 条 → 批量分析）
      │   ├─ ReplyDrawer（AI 草稿 + 编辑 + 复制 + 标记已回复）
      │   └─ SyncBar（输入关键词 → 同步笔记；展开笔记 → 同步评论）
      └─ Tab 差评预警
          ├─ AlertTable（内容 + 触发原因 + 时间 + 处理按钮）
          └─ AcknowledgeAction
```

路由：`/reputation`、`/reputation/:shop_id`。

---

## 9. 安全约束

| 接口 | 约束 |
|---|---|
| 全部 | JWT + shop 所有权 |
| sync / sync-comments | limit ≤ 50；频控 60s；sync 与 sync-comments 独立 key，sync-comments 按 note_id 独立窗口 |
| batch-analyze | 最多 20 条，超限 400；频控 30s |
| ai-reply | 仅 comment 类型；敏感词 422 不占用频控；LLM 成功路径才计 20s 频控 |
| reply | 需要 reply_content 非空 |
| alert ack | 幂等 |

所有频控 key 含 `{user_id}:{shop_id}`，同一门店不同运营互不占用窗口。

---

## 10. MVP 边界

### 包含
- 小红书笔记 + 评论爬虫采集、去重落库
- 评价列表 / 笔记卡片 / 评论行 / 筛选分页
- 批量 AI 情感分类 + 关键词提取（≤20 条/次）
- 评论 AI 回复草稿 + 编辑 + 复制 + 标记已回复
- 差评预警（内置规则）+ 标记处理
- 口碑概览统计

### 不包含（后续迭代）
- 大众点评 / 美团 / 抖音
- 手动导入（manual_imports 是独立的导入记录表，不直接写 reviews；第二阶段解析后统一经 reviews API 落库，与本期新增字段无冲突）
- 自动发布回复
- 定时自动爬虫
- 自定义预警规则
- 口碑周报 / 竞对口碑对比
- 笔记回复草稿（笔记只做分析）

---

## 11. 复用清单

| 能力 | 来源 |
|---|---|
| JWT + shop 所有权 | 装修模块 `_verify_shop_owner` |
| XHS 爬虫 | `XhsCrawler` + `processor.normalize_note/comment` |
| DeepSeek LLM | `app.ai.profile_agent` 同款客户端封装（可抽公共模块） |
| 敏感词过滤 | `app.core.sensitive_filter` |
| 频控 | `app.core.rate_limit` |
