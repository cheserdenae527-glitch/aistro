# 爬虫管理板块 — 设计规约

> 版本：v0.4 · 2026-08-07 · 小红书（XHS）聚焦
> 关联：`docs/PLAN.md` M5 · `docs/PLAN-CRAWLER.md` · `docs/DESIGN-BLOGGER-SCORING-REALDATA.md`
> **代码现状：v0.2 估算版**（分层抽样 + 比例估算的博主分析已实现并在线上运行）。
> v0.4 变更：订正状态标注——本文档中标 **[规划中]** 的内容均为设计方案，尚未写代码；未标注的内容为现状。
> 之前 v0.3 曾将"真实数据版评分"整体写成已完成，与代码不符，本版已订正。

---

## 1. 范围

爬虫管理板块负责：小红书笔记/博主数据抓取、任务调度、博主订阅（含全局订阅入口、轻量定时刷新与更新提醒）、博主数据分析评分（现状：分层抽样估算版；**[规划中]** 真实数据版评分改造）、图片/视频代理，以及对应的前端"爬虫管理"页。

---

## 2. 架构

```
Frontend CrawlJobsPage (/crawl)
  · SubscribeButton（复用组件，接入博主卡片 / 笔记详情 / 分析页头 / 作品与浏览列表）
  · AnalysisTaskPanel（后台分析任务进度条 + 覆盖率/可信度展示，已实现基础版）
        │ REST API (JWT)
        ▼
FastAPI routers
  ├─ /crawl-jobs      任务创建/列表/详情
  ├─ /notes           搜索/详情/评论/博主搜索/博主作品/博主分析（现状：同步接口）
  ├─ /notes/analysis-tasks   博主分析任务创建/查看进度/取消（异步，已实现）
  ├─ /subscriptions   博主订阅 CRUD + refresh + snapshots + status(/batch) + ack
  └─ /images          图片代理（proxy）+ 视频代理（video-proxy）
        │
        ▼
XhsCrawler (services/crawler/xhs)
  ├─ Spider_XHS runtime（签名/防反爬/请求）
  ├─ 随机延时 + 指数退避 + 代理池轮换 + Cookie 健康检测
  └─ processor.normalize_*（标准化 + 计数解析 + 发布时间）
        │
        ├─→ NoteDetailCache（笔记详情快照缓存表，已建 note_details）
        │
        ├─→ xhs_analysis.py（五维评分引擎，纯函数）
        │     现状：分层抽样 + 比例估算（见 §5）
        │     真实数据版基础版已实现：两段式筛选 + 覆盖率可信度 + 异常识别（阈值待标定，见 §11）
        │
        └─→ SubscriptionScheduler（订阅定时刷新，APScheduler 内存调度，预留 Celery Beat 替换点）
              现状：轻量快照刷新 + 深度详情增量同步（已实现基础版）（尚未实现）
```

---

## 3. 数据模型

### 3.1 crawl_jobs（M2 已有）

| 字段 | 说明 |
|---|---|
| id | UUID PK |
| shop_id | UUID FK shops |
| platform | 目标平台 |
| job_type | search / note_detail / comment（已通过迁移 `a7b8c9d0e1f2` 完成，历史枚举 full/incremental 已废弃） |
| status | pending / running / success / failed / cancelled |
| schedule | cron 或 manual |
| result_summary | jsonb |
| error_log / started_at / finished_at / created_at | 任务元数据 |

当前任务运行器为 threading 内存任务，不写 crawl_jobs 表；Redis/Celery 接入后统一落库。

### 3.2 subscriptions / subscription_snapshots

| 表 | 字段要点 |
|---|---|
| subscriptions | id, user_id, xhs_user_id, nickname, avatar, note_count, follower_count, following_count, notified_note_count（上次提醒时的笔记数快照）, last_crawled_at, created_at |
| subscription_snapshots | id, subscription_id FK, note_count, follower_count, following_count, crawled_at |

"有更新"判定：`note_count > notified_note_count` 即视为有新笔记待查看；复用 `subscriptions` 字段 + `subscription_snapshots` 历史即可回溯变化。查看后调用 `ack` 接口将 `notified_note_count` 同步为当前值。

`subscriptions.last_deep_synced_at` 字段已加入；深度详情增量同步已实现基础版：轻量刷新检测到笔记数增加且距上次深度同步≥间隔时，增量补抓详情进 `note_details`（见 §11.6）。

### 3.3 [规划中] note_details（笔记详情快照缓存，尚未建表）

设计草案，字段未最终定稿，仅供 §11 方案参考：

| 字段 | 说明 |
|---|---|
| id | UUID PK |
| xhs_user_id | 所属博主 ID |
| platform_note_id | 笔记 ID（与 xhs_user_id 联合唯一） |
| detail_json | jsonb，完整标准化详情 |
| fetched_at | 抓取时间 |

### 3.4 [规划中] blogger_analysis_tasks（博主分析任务，尚未建表）

设计草案，见 §11。

### 3.5 标准化笔记结构（normalize_note 输出）

| 字段 | 说明 |
|---|---|
| platform_note_id / xsec_token | 笔记 ID 与访问令牌 |
| title / desc / type | 标题 / 正文 / normal 或 video |
| cover_url / image_urls / video_url | 媒体 |
| author | id / nickname / avatar |
| stats | liked / collected / comments / shared |
| tags | corner_tag_info |
| published_at | 发布时间（详情接口才有，列表接口可能为 None） |
| raw | 原始 JSON |

---

## 4. API 设计（现状）

### 4.1 爬虫任务

```
POST  /api/v1/crawl-jobs
  Body: { job_type: search|note_detail|comment, params: { query, limit, note_url } }
  → 校验 / 单用户并发 ≤20 / 返回 { job_id, status: running }

GET   /api/v1/crawl-jobs
  → { running: [任务列表] }

GET   /api/v1/crawl-jobs/{job_id}
  → 任务详情（含 result / error）
```

### 4.2 笔记与博主

```
POST  /api/v1/notes/search-users
  Body: { query, limit ≤ 50 } → { items: [{ user_id, nickname, avatar, fans, notes, desc }] }

POST  /api/v1/notes/search
  Body: { query, limit ≤ 100, sort 0-4, note_type 0-2, time_range 0-3 }
  → { items: [标准化笔记], stats }

GET   /api/v1/notes/{note_id}?xsec_token=...
  → 标准化笔记详情

GET   /api/v1/notes/{note_id}/comments?xsec_token=...
  → { items: [标准化评论] }

GET   /api/v1/notes/users/{user_id}/notes
  → 按博主 ID 取作品列表；内部会用搜索结果补齐部分互动字段，用于"博主作品" Tab

POST  /api/v1/notes/users/{user_id}/analysis
  Body: { nickname, fans, detail_limit 0-50（默认 10）, refresh: false }
  → 分析结果（同步返回，见 §5）
  refresh=true 时跳过缓存强制重新抓取
  说明：前端"快速分析"入口按钮已移除，但 `detail_limit=0` 这条只用列表数据、不抓详情的快速路径在后端仍然保留，未被下线。
```

**[规划中]** 异步分析任务接口 `POST/GET/DELETE .../analysis-tasks`，见 §11.3。原同步接口 `/analysis` **不会**在异步接口上线前废弃，两者会并存一段时间。

### 4.3 订阅

```
POST    /api/v1/subscriptions
GET     /api/v1/subscriptions
POST    /api/v1/subscriptions/{id}/refresh
GET     /api/v1/subscriptions/{id}/notes
GET     /api/v1/subscriptions/{id}/snapshots
DELETE  /api/v1/subscriptions/{id}

GET     /api/v1/subscriptions/status?xhs_user_id=...
  → { subscribed: bool, subscription_id, has_update: bool }

POST    /api/v1/subscriptions/status/batch
  Body: { xhs_user_ids: [...] ≤50 }
  → { items: { xhs_user_id: { subscribed, subscription_id, has_update } } }

POST    /api/v1/subscriptions/{id}/ack
  → 将 notified_note_count 同步为当前 note_count，清除"有更新"标记
```

`/subscriptions/{id}/refresh` 目前只拉取粉丝数/笔记数快照，**不**抓详情。**[规划中]** 深度详情增量同步见 §11.5。

### 4.4 图片 / 视频代理

```
GET /api/v1/images/proxy?url=<encoded>&size=0|1200
  → 仅允许 xiaohongshu.com / xhscdn.com / xhslink.com
  → size>0 放大到指定宽度（LANCZOS，JPEG）
  → 按 IP 限流 60 次/分钟

GET /api/v1/images/video-proxy?url=<encoded>
  → 小红书视频代理播放 + 下载，域名白名单同上
  → 之前版本的 SPEC 遗漏了此接口，本版补上
```

---

## 5. 博主分析评分引擎（现状：分层抽样估算版）

### 5.1 加权互动

```
weighted_engagement = likes×1 + collects×1 + comments×4 + shares×4
```

### 5.2 维度与权重

| 维度 | 权重 | 计算口径 |
|---|---|---|
| 互动质量 | 25% | 近30天加权互动 / 粉丝数（≥8%→100，5%→75，3%→50，1%→20，0→0，分段插值） |
| 内容效能 | 25% | 爆文率 = 加权互动 ≥ 均值3倍的笔记占比（≥20%→100，10%→60，5%→35，0→0） |
| 活跃度 | 15% | 近30天周均发布数（≥3→100，2→75，1→50，≤0.5→25） |
| 稳定性 | 15% | (1 - min(CV, 1)) × 100，CV 来自发布时间间隔 |
| 趋势 | 20% | 近30天平均互动 / 前30天平均互动（增长≥50%→100，持平→60，下降50%→20） |

### 5.3 综合等级

| 分数 | 等级 |
|---|---|
| ≥85 | 卓越 |
| 70-84 | 优秀 |
| 55-69 | 良好 |
| 40-54 | 一般 |
| <40 | 待观察 |

### 5.4 响应结构（现状）

```
{
  nickname, follower_count, note_count,
  date_range: { start, end },
  summary: {
    total_notes, detailed_notes, partial_notes, estimated_notes, candidate_notes, timed_notes,
    avg_likes/comments/collects/shares, total_engagement, avg_engagement,
    engagement_rate, viral_count, viral_rate, like_collect_ratio, structure, viral_peak,
    sample_mode: full|stratified|search|list, sample_size, estimated_count
  },
  dimensions: { interaction_quality, content_effectiveness, activity, stability, trend },
  overall: { score, level, description },
  timeline: { type: weekly|monthly, items: [...] },
  notes: [按时间倒序的完整笔记列表，每条笔记可能带 estimated: true 表示互动数据为估算值],
  insights: [洞察文案],
  source: user_notes|search_fallback|search_quick,
  user_id,
  detail_limit
}
```

评分样本优先取 `full_stats=true` 的详情笔记；全部为列表数据时退化使用列表数据并在洞察中提示覆盖范围。

### 5.5 采样策略（代表性抽样加速，现状实现）

目标：在不显著牺牲代表性的前提下减少详情请求数量，加快分析速度。

| 场景 | 处理方式 |
|---|---|
| 候选笔记总数 ≤ detail_limit | 不做抽样，全部抓详情 |
| 候选笔记总数 > detail_limit | 分层抽样：按发布顺序分桶（桶数 = min(detail_limit/2, 覆盖自然周数)），桶内按点赞数降序抽 1-2 条，并保底覆盖点赞中位数区间 |
| 抽样窗口 | 按"目标笔记篇数"滑动取窗口，而非固定 60 天；覆盖不足篇数时自动扩大回溯天数 |
| 未抓详情笔记 | 用已抓详情笔记拟合 (评论+收藏+分享)/点赞 平均转化比例，估算其加权互动，响应中对应笔记标记 `estimated: true` |
| 早停 | 连续新增样本对当前均值/CV 的影响 < 3% 时提前结束抓取 |
| 低样本量降级 | 候选笔记 < 8 篇时，稳定性/趋势维度标记"样本不足，仅供参考" |
| 趋势维度口径 | 样本充足时沿用"近30天 vs 前30天"；样本不足时改用"近半程 vs 前半程" |

> **重要**：这套抽样估算是当前评分的实际实现。是否要切换到 §11 的"真实数据版"（不估算），需要先确认 §11 方案并排期开发，在那之前评分结果仍会包含 `estimated` 标记的笔记。

---

## 6. 前端页面（现状）

```
路由 /crawl · CrawlJobsPage
├─ Tab 任务列表
│   ├─ 搜索框（历史记录 localStorage aistro_xhs_history）
│   ├─ 排序 / 类型 / 时间 / 条数（可显示三位数字）
│   ├─ 进度条 + 任务表（3 秒轮询）
│   └─ 说明：原"新建任务" Modal 已从前端移除；前端不再提供新建任务入口，创建任务只能直接调 API
├─ Tab 搜索博主
│   ├─ 昵称搜索
│   │   （深度分析条数选择与"快速分析"按钮均已移除；分析改为创建任务 + 进度轮询；同步接口 detail_limit 参数见 §4.2）
│   └─ 博主卡片（查看作品 / 分析 / SubscribeButton：已订阅态 + 有更新红点）
├─ Tab 博主作品
│   ├─ 顶部作者信息条（SubscribeButton）
│   └─ 笔记卡片网格（点击打开详情 Modal，Modal 内作者信息同样带 SubscribeButton）
├─ Tab 浏览结果
│   ├─ 点赞 / 评论 / 收藏排序
│   ├─ 笔记卡片作者信息（SubscribeButton）
│   └─ 保存到历史 / 加载历史（localStorage aistro_browsed）
├─ Tab 博主分析
│   ├─ 页头博主信息（SubscribeButton + 有更新提醒）
│   ├─ 统计卡片（8 张）
│   ├─ 折线趋势图（点赞/评论/收藏/加权互动）
│   ├─ 五维雷达图
│   ├─ 爆款 TOP12 柱状图
│   ├─ 洞察 Alert（含抽样/估算提示）
│   └─ 全部笔记表格（排序 + 点击行查看详情，estimated 笔记标记角标）
│   [规划中] 任务进度条、覆盖率/可信度展示、异常识别 Alert，见 §11.6
└─ Tab 博主订阅
    ├─ 订阅表格（笔记数 / 粉丝数 / 最后更新 / 有更新列 / 刷新 / 取消）
    └─ 添加订阅 Modal

SubscribeButton（复用组件）：内部调用 /subscriptions/status(/batch) 获取状态并本地缓存（TTL 60s），
列表类页面（搜索博主/博主作品/浏览结果）批量渲染时统一走 batch 接口，避免逐个请求。
点击"已订阅+有更新"态时触发 /subscriptions/{id}/ack 清除提醒标记。
```

---

## 7. 配置与防风控（现状）

配置文件：`backend/services/crawler/xhs/scripts/crawler_config.json`

| 字段 | 说明 |
|---|---|
| cookies | 浏览器复制的完整 Cookie Header |
| proxies | 代理池（数组，轮换使用） |
| min_delay / max_delay | 请求随机延时区间（默认 2-5s） |
| max_retries | 失败重试次数（默认 3） |
| subscription_refresh_interval_hours | 订阅轻量快照刷新间隔（默认 12h） |
| subscription_refresh_batch_size | 单次调度批量刷新订阅数上限（默认 20） |

Cookie 更新流程：浏览器登录小红书 → F12 → Application → Cookies → 复制完整 Cookie Header → 写入 `crawler_config.json`。

已内置策略：随机延时、指数退避、代理池轮换、Cookie 健康检测、失败自动重试、分析接口短缓存（15 分钟，refresh 可强制刷新）。

订阅轻量快照刷新：SubscriptionScheduler 按 `subscription_refresh_interval_hours` 触发，复用 `/subscriptions/{id}/refresh` 内部服务方法，仍受随机延时/退避/代理池轮换约束，按 `subscription_refresh_batch_size` 分批执行；当前为进程内 APScheduler 调度，非持久化。

`analysis_batch_size` / `analysis_batch_interval_seconds` / `analysis_max_notes_per_task` / `analysis_task_timeout_minutes` / `subscription_deep_sync_min_interval_hours` / `subscription_deep_sync_max_per_run` / `min_follower_count` / `min_note_count` / `min_avg_likes` 已加入 `crawler_config.json`（初版默认值，待 §8 标定后替换）。

---

## 8. 安全约束（现状）

| 接口 | 约束 |
|---|---|
| 全部业务 API | JWT 鉴权 |
| /images/proxy /images/video-proxy | 仅 https + 域名白名单；按 IP 60 次/分钟；单图 ≤20MB |
| /crawl-jobs | 单用户运行中任务 ≤20 |
| /notes/search | limit ≤100 |
| /notes/users/{id}/analysis | detail_limit ≤50 |
| /subscriptions/status/batch | 单次 xhs_user_ids ≤50 |
| 订阅轻量快照刷新 | 与手动 refresh 共享单用户并发限制 |

`/notes/users/{id}/analysis-tasks` 已实现：创建/进度查询/取消；并发限制与订阅深度同步节奏沿用批次参数（见 §11）。

---

## 9. MVP 边界

### 包含（现状已实现）
- 小红书笔记 / 博主 / 评论 / 详情抓取与标准化
- 爬虫任务（搜索 / 详情 / 评论）与状态查看
- 博主搜索、作品浏览、订阅长期观察
- 全局订阅按钮（博主卡片 / 作品与浏览列表 / 笔记详情 / 分析页头复用组件）+ 批量订阅状态查询
- 订阅轻量快照定时刷新与"有更新"提醒（APScheduler 内存调度）
- 博主五维评分（分层抽样 + 比例估算版）、趋势图表、全部笔记数据提取
- 图片 / 视频代理与高清放大

### 不包含（后续迭代 / [规划中]）
- 美团 / 抖音 / 大众点评爬虫
- Celery / Redis 持久化任务队列（当前 threading 内存任务）
- 通用爬虫任务定时化调度
- 图片 / 视频批量下载入库（MinIO/OSS 当前仅预留）
- 爬虫 / 订阅 / 分析按 shop_id 关联回门店体系（当前按 user_id）
- 竞对博主对比分析
- 多平台数据统一入库（platform_shops / reviews）
- 博主真实数据版评分（两段式筛选 + 覆盖率可信度 + 异常识别 + 后台分析任务 + 详情快照缓存，基础版已实现；阈值与异常量化待标定）
- 订阅深度详情增量同步（已实现基础版）

---

## 10. 已知限制（现状）

- 小红书 user_posted 列表接口只返回点赞数，不返回发布时间 / 评论 / 收藏；完整数据需逐条调详情接口，因此分析接口通过 `detail_limit` 控制深度。
- 小红书风控间歇表现：user_posted 返回 `data:null`、JS x-rap-param 生成失败；已做重试 + 搜索兜底 + 短缓存，连续失败通常需要更新 Cookie。
- 订阅需保存完整 `xhs_user_id`（来自搜索接口的 `id`），历史数据存在截断 ID 导致刷新失败的案例；清洗 / 修复已登记到 PLAN-CRAWLER.md 技术债。
- 任务运行器为内存态，服务重启后任务丢失；后续接 Redis/Celery 并落库 crawl_jobs。
- 爬虫 / 订阅 / 分析当前按 user_id 隔离，未挂 shop_id；并入门店聚合前需补 shop 关联。
- MinIO/OSS 暂未接入爬虫，图片仅实时代理不落盘。
- 前端 `npm run build` 被 `ProfileEditorPage.test.tsx` 类型错误阻塞，暂用 `npx vite build`（技术债已登记）。
- 订阅定时刷新为进程内 APScheduler 调度，服务重启后调度计划丢失，需在启动时从 subscriptions 表重建；后续接 Celery Beat 后此限制解除。
- 分析结果中的 `estimated` 笔记为按比例拟合的估算值，在博主发布节奏剧烈波动或存在异常点赞（如刷量）时可能偏差较大；对精度敏感场景（尤其是"筛选优质/低质博主"这类决策场景）建议先看 §11 的真实数据版方案，评估是否需要优先排期。
- `/subscriptions/status/batch` 单次上限 50，博主数较多的列表页需前端分批调用。

---

## 11. 真实数据版评分改造（基础版已实现；初版阈值已回填 2026-08-08，待人工复核）

> 基础版已实现（模型/任务/引擎/前端），分层互动质量阈值已按 2026-08-08 初版标定回填到 `blogger_scoring.py`（样本 T1=12/T2=12/T3=11/T4=4，待人工复核）；原始设计稿：`docs/DESIGN-BLOGGER-SCORING-REALDATA.md`。

### 11.1 核心原则

评分只使用真实抓取到的详情数据；缺失就是缺失，绝不估算、不外推。目标场景：用博主分析筛选优质达人、过滤低质账号——这类决策场景对估算误差的容忍度低于"看趋势"场景，因此不能沿用 §5.5 的抽样估算。

### 11.2 两段式筛选流程

```
第 1 段：列表粗筛（成本低，不做评分，不消耗详情请求）
  ├─ 粉丝数 ≥ min_follower_count（默认 1000）
  ├─ 笔记数 ≥ min_note_count（默认 10）
  ├─ 列表平均赞 ≥ min_avg_likes（默认 50）
  └─ 通过 → 创建分析任务；不通过 → 直接返回 { passed_prescreen: false }

第 2 段：真实深筛（只对通过粗筛的账号执行，后台任务跑）
  ├─ 优先查详情快照缓存（note_details），命中的直接复用
  ├─ 缓存未命中的按 analysis_batch_size（默认 50/批）分批抓真实详情
  ├─ 单次任务最多抓 analysis_max_notes_per_task（默认 500）篇详情
  ├─ 任务超时 analysis_task_timeout_minutes（默认 45 分钟）：按当前覆盖率出 partial 结果
  ├─ 计算五维评分 + 可信度 + 异常识别
  └─ 输出：评级 + 可信度 + 筛选建议
```

### 11.3 异步分析任务 API（设计）

```
POST  /api/v1/notes/users/{user_id}/analysis-tasks
GET   /api/v1/notes/users/{user_id}/analysis-tasks/{task_id}
DELETE /api/v1/notes/users/{user_id}/analysis-tasks/{task_id}
```

详细请求/响应结构、覆盖率与可信度字段、`blogger_analysis_tasks` 表结构，开发时以本节 + `DESIGN-BLOGGER-SCORING-REALDATA.md` 为准，实现过程中如有调整需同步回本文档。

### 11.4 数据可信度

| 覆盖情况 | 可信度 | 结论 |
|---|---|---|
| 覆盖率 ≥80% 且 ≥30 篇 | 高 | 可正常评级 |
| 覆盖率 ≥50% 且 ≥15 篇 | 中 | 可评级，标注"样本有限" |
| 低于以上 | 低 | 不评级，"数据不足，暂不评分" |

### 11.5 异常识别（量化阈值，初版默认值，开发时需压测校准）

| 异常 | 判定 |
|---|---|
| 刷量嫌疑 | 单篇 (评论+收藏+分享)/点赞 < 0.5%，且点赞 ≥ 真实样本中位数 3 倍 |
| 粉丝互动倒挂 | 真实加权互动 / 粉丝数 < 1% |
| 发布停滞 | 最新真实笔记发布时间距今 > 60 天 |
| 数据异常波动 | 近半程 vs 前半程真实平均加权互动比值 > 300% 或 < 30% |

### 11.6 订阅深度详情同步（已实现基础版）

轻量快照刷新检测到笔记数增加、且距上次深度同步 ≥ `subscription_deep_sync_min_interval_hours`（默认 24h）时触发，只增量抓新增笔记详情，写入 note_details 缓存。与分析任务共用 `analysis_batch_size` / `analysis_batch_interval_seconds` 节奏，不额外突破风控。

### 11.7 前端改造点（设计）

- 任务进行中：进度条 + 预估剩余时间，不展示评级
- 任务完成：覆盖率展示 + 可信度徽标；低可信度显示"数据不足，暂不评分"
- 移除"估算"标签及相关文案；新增异常识别 Alert
- 筛选结果视图：按综合分、可信度、粉丝数、粉丝互动率排序
