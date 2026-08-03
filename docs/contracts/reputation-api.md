# 口碑管理板块 API 契约

> 版本：v0.1 · 对应 R1 后端实现
> 基线：docs/SPEC-REPUTATION.md v0.1 / docs/PLAN-REPUTATION.md R1

所有接口前缀 `/api/v1`，全部需要 JWT（`Authorization: Bearer <token>`），并校验
`shop -> merchant -> user` 所有权；非所有者一律 404。

## 1. 数据语义

| review_type | rating | reply_status | 说明 |
|---|---|---|---|
| note | NULL | NULL | 笔记，只做口碑分析，不生成回复 |
| comment | NULL | unreplied / ai_replied / manual_replied | 评论，可生成回复草稿 |
| rating_review | 1-5 | 同上 | 大众点评/美团预留 |

去重键：`(platform_shop_id, review_type, platform_review_id)` 唯一索引，重复同步直接跳过。

## 2. 评价列表

```http
GET /shops/{shop_id}/reviews
    ?review_type=note|comment|rating_review
    &sentiment=positive|neutral|negative
    &reply_status=unreplied|ai_replied|manual_replied
    &alert_status=none|triggered|acknowledged
    &keyword=<文本>
    &parent_review_id=<笔记 review id>
    &date_from=<ISO datetime>
    &date_to=<ISO datetime>
    &page=1
    &size=20
```

所有筛选参数可选。`keyword` 匹配 `content` 或 `note_title`。响应：

```json
{
  "items": [
    {
      "id": "uuid",
      "platform_shop_id": "uuid",
      "platform_review_id": "5d2f...",
      "reviewer_name": "探店博主",
      "rating": null,
      "content": "这家店分量少",
      "tags": null,
      "sentiment": null,
      "reply_status": null,
      "ai_reply": null,
      "reply_content": null,
      "replied_at": null,
      "reviewed_at": null,
      "review_type": "note",
      "parent_review_id": null,
      "note_title": "避雷",
      "note_url": "https://www.xiaohongshu.com/explore/...",
      "author_id": "user-1",
      "author_avatar": "",
      "interact_stats": {"liked": 5, "collected": 2, "comments": 3, "shared": 1},
      "source_json": {},
      "alert_status": "triggered",
      "alert_reason": {"type": "keyword", "keywords": ["分量少"], "sentiment": null},
      "created_at": "2026-08-03T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

## 3. 概览摘要

```http
GET /shops/{shop_id}/reviews/summary
```

响应：

```json
{
  "note_count": 12,
  "comment_count": 48,
  "rating_review_count": 0,
  "sentiment_counts": {"positive": 20, "neutral": 15, "negative": 5, "unanalyzed": 20},
  "unreplied_count": 10,
  "alert_count": 3
}
```

`unreplied_count` 只统计 `review_type=comment AND reply_status='unreplied'`，笔记不计入。

## 4. 小红书笔记同步

```http
POST /shops/{shop_id}/reviews/sync/xiaohongshu
Content-Type: application/json
```

Body：

```json
{ "keyword": "火锅", "limit": 20 }
```

`limit` 范围 1-50，默认 20。频控 key：`rate_limit:sync_notes:{user_id}:{shop_id}`，60 秒。

响应：

```json
{ "created": 5, "skipped": 2 }
```

落库时同步执行关键词扫描；命中即写 `alert_status=triggered` 和
`alert_reason={type:"keyword", keywords:[...], sentiment:null}`。

## 5. 笔记评论同步

```http
POST /shops/{shop_id}/reviews/{rid}/sync-comments
```

无 Body；`{rid}` 必须是本店 `review_type=note` 的记录，否则 400。
频控 key：`rate_limit:sync_comments:{user_id}:{shop_id}:{note_id}`，60 秒，不同笔记互不阻塞。

响应：

```json
{ "created": 10, "skipped": 3 }
```

## 6. 批量情感分析

```http
POST /shops/{shop_id}/reviews/batch-analyze
Content-Type: application/json
```

Body：

```json
{ "review_ids": ["uuid1", "uuid2"] }
```

最多 20 条，超过返回 400。频控 key：`rate_limit:batch_analyze:{user_id}:{shop_id}`，30 秒。
后端每批 ≤10 条调用 DeepSeek，单批失败不影响其他批次。

响应：

```json
{
  "analyzed": [
    {"id": "uuid1", "sentiment": "negative", "tags": ["分量少"]}
  ],
  "failed": ["uuid2"],
  "total": 2,
  "success_count": 1,
  "failed_count": 1
}
```

`sentiment` 会写入 `reviews.sentiment`；判为 negative 时按状态机触发/合并预警。

## 7. AI 回复草稿

```http
POST /shops/{shop_id}/reviews/{rid}/ai-reply
```

仅 `review_type=comment`，笔记返回 400。输入为评论内容 + 门店信息（店名/品类/定位）。

校验顺序：评论内容敏感词 422 → 频控检查 → LLM 生成 → 生成稿敏感词 422 →
成功路径写入频控 key。

频控 key：`rate_limit:ai_reply:{user_id}:{shop_id}`，20 秒。敏感词 422 不占窗口。

响应：

```json
{ "id": "uuid", "ai_reply": "非常抱歉这次体验不好，我们已加强服务培训，欢迎再次光临。", "reply_status": "ai_replied" }
```

写入 `ai_reply`，`reply_status=ai_replied`。草稿不会自动发布。

## 8. 确认回复

```http
PUT /shops/{shop_id}/reviews/{rid}/reply
Content-Type: application/json
```

Body：

```json
{ "reply_content": "已回复给用户的内容" }
```

`review_type=note` 返回 400。写入 `reply_content`、`reply_status=manual_replied`、
`replied_at=now`；`alert_status=triggered` 时自动流转为 `acknowledged`。
已 `manual_replied` 的记录允许重复调用覆盖内容并刷新 `replied_at`。

## 9. 差评预警

### 9.1 预警列表

```http
GET /shops/{shop_id}/reviews/alerts
```

只返回 `alert_status=triggered` 的记录（含 `alert_reason` 触发时快照），响应结构同
§2 单条评价。

### 9.2 处理

```http
POST /shops/{shop_id}/reviews/alerts/{rid}/ack
```

状态机：

```text
none ──触发──→ triggered ──ack──→ acknowledged
                 │                    ▲
                 │                    │
                 └──manual_replied────┘
```

- `none` 调 ack：400
- `triggered` 调 ack：200，状态变 `acknowledged`
- `acknowledged` 重复调 ack：200，幂等
- ack 后重新分析不回跳、不改写 `alert_reason`

响应：

```json
{ "id": "uuid", "alert_status": "acknowledged" }
```

### 9.3 alert_reason 结构

```json
{ "type": "keyword", "keywords": ["卫生", "分量少"], "sentiment": null }
```

```json
{ "type": "sentiment", "keywords": [], "sentiment": "negative" }
```

```json
{ "type": "both", "keywords": ["分量少"], "sentiment": "negative" }
```

`alert_reason` 是触发时快照，重新分析只更新 `reviews.sentiment`，不改写快照。

## 10. 错误约定

| 状态码 | 场景 |
|---|---|
| 400 | batch-analyze >20 条；ai-reply 目标不是 comment；reply 目标是 note；ack 未触发记录 |
| 401 | 未登录/无效 token |
| 404 | shop 非本人、review 不属于该 shop |
| 422 | 敏感词命中（ai-reply 输入或生成稿） |
| 429 | 频控命中（sync 60s / batch-analyze 30s / ai-reply 20s） |
| 502 | 爬虫失败；LLM 调用失败 |

爬虫错误区分：

- cookie 失效：detail 含 `登录态失效，请更新 cookie`
- `xsec_token` 过期：detail 含 `笔记链接已过期，请重新同步该笔记`
- 无法区分时返回原始错误信息，不吞细节

## 11. 频控 key 汇总

| 接口 | key | TTL |
|---|---|---|
| 同步笔记 | `rate_limit:sync_notes:{user_id}:{shop_id}` | 60s |
| 同步评论 | `rate_limit:sync_comments:{user_id}:{shop_id}:{note_id}` | 60s |
| 批量分析 | `rate_limit:batch_analyze:{user_id}:{shop_id}` | 30s |
| AI 回复 | `rate_limit:ai_reply:{user_id}:{shop_id}` | 20s |

同一门店不同运营各自独立窗口，互不占用。
