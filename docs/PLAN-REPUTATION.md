# 口碑管理板块 — 实现计划

> 基于 SPEC-REPUTATION v0.1 · 独立于主项目里程碑

## 依赖与复用

| 能力 | 来源 | 状态 |
|---|---|---|
| reviews 表 | 已存在，需新增字段迁移 | 已建 |
| XHS 爬虫（搜索/评论） | `XhsCrawler` + processor | 已有 |
| DeepSeek LLM | 装修模块客户端模式 | 已有 |
| 敏感词 / 频控 / 鉴权 | core 模块 | 已有 |

---

## R1 — 后端：迁移 + API + AI 服务 + 爬虫同步

**目标**：评价采集、分析、回复、预警全部 API 可用。

### 任务清单

1. Alembic 迁移：reviews 新增字段
   - review_type / parent_review_id / note_title / note_url / author_id / author_avatar
   - interact_stats / source_json / alert_status / alert_reason
   - reply_status 改为 nullable（note 类型置 NULL）
   - **先做数据体检**：历史记录回填 review_type=rating_review；检查
     (platform_shop_id, platform_review_id) 重复/空值冲突，清理后再建
     唯一索引 (platform_shop_id, review_type, platform_review_id)
2. SQLAlchemy 模型 + Pydantic Schema 更新
3. API：
   - GET /reviews（筛选 + 分页）
   - GET /reviews/summary（概览统计）
   - POST /reviews/sync/xiaohongshu（limit ≤ 50，频控 key 独立）
   - POST /reviews/{rid}/sync-comments（频控 key 与 sync 独立）
   - POST /reviews/batch-analyze（≤20 条超限 400；部分失败返回 analyzed+failed）
   - POST /reviews/{rid}/ai-reply（仅 comment，草稿 + 敏感词过滤）
   - PUT /reviews/{rid}/reply（确认回复；triggered 自动流转 acknowledged）
   - GET /reviews/alerts（返回 alert_reason）+ POST /reviews/alerts/{rid}/ack
4. AI Service：ReviewAgent
   - 情感 + 关键词批量分析（LLM 分批）
   - 评论回复草稿生成（好评/差评模板 + 商家信息）
   - 预警双路径：落库关键词扫描（无需 LLM）+ 分析后 negative 补充触发
   - alert_reason 持久化（keyword / sentiment / both）
   - 状态机：ack 后不自动回跳；manual_replied 自动 acknowledged
5. 爬虫同步服务：XHS 笔记/评论去重落库（复用 processor）
   - 落库时同步关键词扫描并写 alert_status/alert_reason
   - 错误区分：cookie 失效 vs xsec_token 过期
6. 鉴权 / 频控（key 含 user_id+shop_id）/ 敏感词
7. 测试：
   - 去重：重复同步不产生重复记录
   - batch-analyze：超过 20 条拒绝；频控 429（mock LLM）
   - ai-reply：note 类型 400；comment 正常生成；敏感词草稿拒绝
   - ai-reply 敏感词 422 不占用频控窗口（立即重试成功）
   - reply：note 类型 400；triggered 评论回复后自动 acknowledged
   - 预警：同步落库关键词立即触发（不依赖 batch-analyze）
   - 预警：negative 补充触发、ack 幂等、ack 后重新分析不回跳
   - 预警：none 状态 ack 返回 400
   - 预警：先后命中合并 alert_reason（keyword → both），acknowledged 后 reason 不再更新
   - 预警：manual_replied 自动 acknowledged
   - 预警：triggered 记录重新分析为 positive 不撤销（只升不降），reason.type 保持并集
   - 预警：重新分析只更新 reviews.sentiment，alert_reason 快照不变（方案 B）
   - 列表：GET /reviews 支持 alert_status 筛选
   - 迁移：历史数据回填后唯一索引不冲突
   - 频控：sync 与 sync-comments key 互相独立
   - 频控：sync-comments 不同笔记 id 互不阻塞（key 含 note_id）
   - reply：已 manual_replied 重复调用允许覆盖并更新 replied_at
   - summary：未回复数只计 comment+unreplied，笔记不计入
   - 鉴权 401 / 跨用户 404
8. 契约文档：`docs/contracts/reputation-api.md`
   - 路径与 SPEC §6/§7 完整前缀核对（/api/v1/shops/{shop_id}/reviews/...）
   - batch-analyze 部分失败响应结构、alert_reason 结构写进契约

### 交付物
- Swagger 可调用全部 API
- pytest 全绿 + 契约文档

---

## R2 — 前端口碑工作台

**目标**：评价列表、批量分析、AI 回复、预警处理完整可用。

```
前置：R1
```

### 任务清单

1. 路由 `/reputation` + `/reputation/:shop_id`，侧边栏入口
2. 门店选择页
3. SummaryCards 概览
4. Tab 评价列表：
   - FilterBar + 分页
   - NoteCard（标题/正文/互动/评论数，展开评论区）
   - CommentRow（作者/内容/情感标签/回复状态）
5. SyncBar：输入关键词同步笔记；笔记展开同步评论（429 提示）
6. BatchAnalyzeBar：勾选 ≤20 条 → 批量分析 → 刷新情感标签
   - 部分失败：展示 failed 列表 + 重试按钮
7. ReplyDrawer：AI 草稿 + 编辑 + 复制 + 标记已回复
   - 标记已回复后预警列表自动移除该条
8. Tab 差评预警：AlertTable + ack 按钮
9. 真实 API 联调（非 mock）：Swagger 反查契约文档，不一致回写
10. 单元测试（Vitest）：筛选条件构造、勾选上限、回复状态切换

### 交付物
- 笔记/评论列表、批量分析、回复、预警全流程可用
- 429/422 错误提示

---

## R3 — 集成验证

**目标**：端到端跑通"同步 → 分析 → 回复 → 预警处理"。

```
前置：R1 + R2
```

### 任务清单

1. 用真实小红书 cookie 验证笔记搜索 + 评论拉取落库
2. 批量分析真实数据（情感/关键词结果检查）
3. AI 回复草稿真实生成 + 复制流程
4. 差评预警触发 + ack
5. 重复同步幂等验证
6. 契约一致性反查 + 文档回写
7. xsec_token 过期与 cookie 失效的错误提示区分验证

### 交付物
- 完整流程可演示
- 爬虫依赖 cookie，验证时需有效登录态

---

## 执行顺序

```
R1 (后端) → R2 (前端工作台) → R3 (真实数据集成验证)
```

每阶段独立对话，R2/R3 引用 `docs/contracts/reputation-api.md`。

## 已知妥协

- 爬虫依赖小红书 cookie 有效，失效时同步返回 502
- MVP 只做手动同步，定时爬虫后补
- 预警用内置关键词，不做规则配置
- 笔记不生成回复草稿（只分析）
