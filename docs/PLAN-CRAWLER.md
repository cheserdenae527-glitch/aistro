# 爬虫管理板块 — 实现计划

> 对应主计划 M5（Crawler Integration）· 独立板块文档
> 当前聚焦：小红书（XHS）爬虫 + 任务调度 + 博主运营数据分析
> **状态说明**：本文档按"已完成 / 规划中"明确标注每一项，避免设计方案被误读为已交付。C9 为设计方案，尚未开发。

## 依赖与复用

| 能力 | 来源 | 状态 |
|---|---|---|
| FastAPI + JWT 鉴权 | M1 认证模块 | 已有 |
| crawl_jobs / subscriptions 表 | M2 数据模型 | 已有（含 subscriptions/snapshots，M5 补建） |
| Spider_XHS 运行时 | `services/crawler/xhs/scripts/runtime/spider_xhs_core` | 已集成 |
| Recharts 图表 | 前端依赖 | 已装 |
| PostgreSQL / Redis | docker-compose | 已有 |
| APScheduler | 订阅轻量快照定时刷新调度 | 已集成（进程内内存态，预留 Celery Beat 替换点） |
| [规划中] note_details / blogger_analysis_tasks 表 | C9 设计方案 | 未建表 |

---

## C1 — XHS 爬虫封装与任务调度

**状态**：已完成

### 任务清单

1. `BaseCrawler` + `CrawlResult` 统一接口
2. `XhsCrawler` 封装 Spider_XHS 运行时：
   - `search_notes` / `search_users` / `get_user_info` / `get_user_notes` / `get_note_detail` / `get_comments` / `check_cookie`
   - 随机延时 + 指数退避 + 代理池轮换 + Cookie 健康检测 + 失败重试
3. 任务运行器 `crawler/tasks.py`（threading 内存任务，预留 Redis/Celery 替换点）：
   - 任务类型：`search`（搜索笔记）/ `note_detail`（笔记详情）/ `comment`（获取评论）
   - 参数校验、单用户并发上限 20、失败状态回写
4. 数据清洗 `crawler/processor.py`：
   - `normalize_note` / `normalize_comment` / `normalize_user`
   - 计数解析（`10万+` / `1.2万` / `3千`）、发布时间提取 `published_at`

### 交付物
- Swagger 可创建/查看爬虫任务
- 前端任务列表 3 秒轮询查看状态与结果

**说明**：前端原"新建任务" Modal 已从任务列表 Tab 移除，当前前端不再提供新建任务入口，创建任务只能直接调 API；文档口径已同步（SPEC-CRAWLER.md §6）。

---

## C2 — 笔记浏览 API 与前端结果页

**状态**：已完成

### 任务清单

1. `POST /notes/search`：关键词 / 数量（≤100）/ 排序 / 类型 / 时间范围
2. `GET /notes/{id}`：笔记详情（需 `xsec_token`）
3. `GET /notes/{id}/comments`：笔记评论（需 `xsec_token`）
4. `GET /notes/users/{user_id}/notes`：按博主 ID 取作品列表，搜索结果合并补齐部分互动字段（此前遗漏未写入 PLAN-CRAWLER，本版补上）
5. `GET /images/proxy`：图片代理（域名白名单 + 高清 resize）
6. `GET /images/video-proxy`：视频代理播放 + 下载（此前遗漏未写入 PLAN-CRAWLER，本版补上）
7. 前端浏览结果 Tab：
   - 点赞 / 评论 / 收藏排序
   - 保存到浏览历史、加载历史（localStorage）

---

## C3 — 博主搜索 / 作品 / 订阅

**状态**：已完成

### 任务清单

1. `POST /notes/search-users`：按昵称搜索小红书博主
2. 博主卡片：查看作品 / 分析 / 订阅
3. `POST /notes/users/{user_id}/analysis`：博主数据分析（同步接口，见 C7）
4. subscriptions CRUD：
   - `POST/GET /subscriptions`、`DELETE /subscriptions/{id}`
   - `POST /subscriptions/{id}/refresh`（拉取粉丝数/笔记数 + 快照，**不**抓详情）
   - `GET /subscriptions/{id}/notes`、`GET /subscriptions/{id}/snapshots`
5. 前端订阅表格：笔记数 / 粉丝数 / 最后更新 / 刷新 / 取消

---

## C4 — 前端爬虫管理页

**状态**：已完成

```
路由 /crawl · CrawlJobsPage
├─ Tab 任务列表（进度/任务表；"新建任务" Modal 已移除，见 C1 说明）
├─ Tab 搜索博主（昵称搜索；深度分析条数选择与"快速分析"按钮已随任务模式移除）
├─ Tab 博主作品（笔记卡片网格）
├─ Tab 浏览结果（筛选排序 + 保存/加载历史）
├─ Tab 博主分析（评分 + 图表 + 全部笔记表格）
└─ Tab 博主订阅（订阅表格 + 添加/刷新/取消）
```

---

## C5 — 防风控与配置

**状态**：基础版已完成，需持续维护

1. `services/crawler/xhs/scripts/crawler_config.json`：
   - `cookies` / `proxies` / `min_delay` / `max_delay` / `max_retries`
   - `subscription_refresh_interval_hours` / `subscription_refresh_batch_size`
2. Cookie 失效时从浏览器 F12 → Application → Cookies 复制完整 Cookie Header 写入配置
3. 已知风控形态：user_posted 返回 `data:null`、JS x-rap-param 间歇失败
   - 已处理：重试 + 搜索兜底 + 短缓存 + 深度详情按需抓取

---

## C6 — 订阅按钮全局化 + 轻量定时刷新与更新提醒

**状态**：已完成（仅轻量快照部分；深度详情同步未做，见 C9）

### 任务清单

1. 前端 `SubscribeButton` 复用组件，接入：搜索博主卡片、博主作品作者信息条、浏览结果笔记卡片作者信息、笔记详情 Modal、博主分析页头
2. `GET /subscriptions/status`、`POST /subscriptions/status/batch`：订阅状态 + "有更新"标记查询（前端本地缓存 TTL 60s，列表页统一走 batch 避免 N+1）
3. `POST /subscriptions/{id}/ack`：查看后清除"有更新"标记
4. `subscriptions.notified_note_count` 字段：记录上次提醒对应的笔记数快照，与当前 `note_count` 对比判定是否有更新
5. `SubscriptionScheduler`（APScheduler 内存调度）：按 `subscription_refresh_interval_hours`（默认 12h）批量刷新订阅**粉丝数/笔记数**，复用现有 `refresh` 服务方法；批量大小受 `subscription_refresh_batch_size`（默认 20）限制
6. 订阅表格新增"有更新"列

### 交付物
- 任意展示博主信息的位置均可一键订阅/取消，且能看到"已订阅"与"有更新"状态
- 订阅列表无需手动点刷新，定时任务自动更新粉丝数/笔记数快照并标记更新

### 明确不含
- 深度详情增量同步（检测到更新后自动补抓笔记详情）——这部分在 v0.3 文档中曾被误标为已完成，实际未实现，规划见 C9
- `subscriptions.last_deep_synced_at` 字段——未加入表结构

---

## C7 — 博主分析评分（现行版本：分层抽样估算）

**状态**：已完成，**当前线上运行的版本**

> 说明：这就是此前文档中反复提到的"分层抽样加速"方案，是当前真正在跑的评分逻辑。C9 是它的替代设计方案，尚未开发；在 C9 落地之前，评分结果仍会包含 `estimated` 标记的笔记。

### 任务清单

1. 评分引擎 `app/services/xhs_analysis.py`：
   - 加权互动 = 赞×1 + 藏×1 + 评论×4 + 分享×4
   - 五维评分：互动质量 25% / 内容效能 25% / 活跃度 15% / 稳定性 15% / 趋势 20%
   - 综合等级：卓越 / 优秀 / 良好 / 一般 / 待观察
   - 周/月时间轴、爆文识别、排序笔记、洞察文案
2. 分析接口 `POST /notes/users/{user_id}/analysis`（同步）：
   - `detail_limit` 控制深度抓取详情条数（0-50，默认 10）
   - 候选笔记总数 > detail_limit 时走分层抽样：按发布顺序分桶 + 桶内按点赞排序抽样
   - 未抓详情的笔记用已抓样本拟合转化比例估算互动，响应标记 `estimated`
   - 早停：连续新增样本对均值/CV 影响 <3% 时提前结束抓取
   - 低样本量（<8 篇）时对应维度标注"样本不足，仅供参考"
   - 失败兜底：重试 → 按昵称搜索 → 15 分钟结果缓存（refresh 可强制刷新）
3. 前端博主分析 Tab：
   - 统计卡片、折线趋势图、五维雷达图、爆款 TOP12 柱状图、洞察列表（含估算提示）、可排序笔记表格（estimated 角标）

### 交付物
- 真实小红书博主 242 篇作品完成评分与时间轴输出（已验证）

---

## C8 — crawl_jobs.job_type 迁移

**状态**：已完成

`crawl_jobs.job_type` 表枚举已通过迁移 `a7b8c9d0e1f2` 从历史的 `full/incremental` 改为 `search/note_detail/comment`，与实际任务类型一致。此前文档中"落库前需迁移"的表述已过时，本版订正。

---

## C9 — 博主真实数据评分改造（基础版已实现，阈值待标定）

**状态**：基础版已实现（note_details / blogger_analysis_tasks / 异步任务 / 真实评分引擎 / 前端任务视图）。分层互动质量阈值已按 2026-08-08 初版标定回填（样本 T1=12/T2=12/T3=11/T4=4，待人工复核）。原始设计稿：`docs/DESIGN-BLOGGER-SCORING-REALDATA.md`。

> 背景：C7 的分层抽样估算方案用于通用速度优化场景是合理的，但用于"筛选优质/低质博主"的决策场景时，估算误差会被放大成错误的筛选结论。本方案目标：评分只使用真实抓取到的数据，缺失就是缺失，绝不估算、不外推。**此状态描述是本文档与 PLAN.md 的唯一权威版本——如果其他文档对 C9/C8 的状态有不同表述，以本条为准。**

### 计划任务清单（未开始）

1. 移除估算逻辑：删除分层抽样、比例拟合、`estimated` 标记相关代码；评分只消费详情缓存中的真实详情
2. 两段式筛选：列表粗筛（不消耗详情请求）+ 真实深筛（只对通过粗筛的账号跑）
3. 新建 `note_details` 表（详情快照缓存），按 `xhs_user_id + platform_note_id` 落库，分析任务优先查缓存
4. 新建 `blogger_analysis_tasks` 表 + 异步接口：`POST/GET/DELETE /notes/users/{user_id}/analysis-tasks`
5. 评分引擎重构：五维评分仅消费真实样本，趋势维度改为"近半程 vs 前半程"
6. 数据可信度：覆盖率≥80%且≥30篇→高；≥50%且≥15篇→中；否则→低（不评级）
7. 异常识别：刷量嫌疑 / 粉丝互动倒挂 / 发布停滞 / 数据异常波动（量化阈值见 SPEC-CRAWLER.md §11.5）
8. 订阅深度详情同步：轻量刷新检测到更新后增量补抓详情，`subscriptions.last_deep_synced_at` 防抖
9. 前端博主分析 Tab 改造：任务进度、覆盖率/可信度展示、异常识别 Alert、去估算标签

### 计划中的默认参数（未写入配置文件，开发时需先加进 crawler_config.json）

`analysis_batch_size`(50) / `analysis_batch_interval_seconds`(15) / `analysis_max_notes_per_task`(500) / `analysis_task_timeout_minutes`(45) / `subscription_deep_sync_min_interval_hours`(24) / `min_follower_count`(1000) / `min_note_count`(10) / `min_avg_likes`(50)

以上均为初版估算值，开发排期确定后需先压测校准，压测重点：批次间隔是否触发风控、500 篇上限任务能否在超时时间内完成。

### 验收方式（未开始）
C9 开发完成后，需用一批人工标注的优质/低质账号验证筛选准确率；具体标注规模和准确率门槛尚未定义，需要在排期时补充。

---

## 测试与契约

| 项 | 位置 | 状态 |
|---|---|---|
| 评分引擎单测 | `backend/tests/test_xhs_analysis.py` | 已有（覆盖 C7 现行抽样估算逻辑） |
| 前端构建 | `npx vite build`（`npm run build` 受 ProfileEditorPage.test.tsx 历史类型错误阻塞） | 已有，阻塞未解 |
| UI 验证 | Playwright：登录 → 搜索博主 → 分析 → 图表渲染断言；订阅按钮点击 → 列表出现 → 定时刷新后"有更新"标记 | 已有 |
| API 契约 | 本文件 + `docs/SPEC-CRAWLER.md` | 已有 |
| [规划中] 分析任务单测 | `backend/tests/test_analysis_task_runner.py` | **文件不存在**，C9 开发时新建 |
| [规划中] 订阅深度同步单测 | `backend/tests/test_subscription_scheduler.py`（深度同步部分） | **文件不存在**，C9 开发时新建 |

---

## MVP 边界

### 包含（现状已实现）
- 小红书笔记 / 博主 / 评论 / 详情爬取与标准化
- 爬虫任务（搜索 / 详情 / 评论）创建与状态查看
- 博主搜索、作品浏览、订阅长期观察
- 全局订阅按钮 + 批量订阅状态查询 + 订阅轻量定时刷新与更新提醒（C6）
- 博主五维评分（分层抽样估算版，C7）、趋势图表、全部笔记数据提取
- 图片 / 视频代理与高清放大

### 不包含（后续迭代 / [规划中]）
- 美团 / 抖音 / 大众点评爬虫
- Celery / Redis 持久化任务队列（当前 threading / APScheduler 内存任务）
- 通用爬虫任务定时化调度
- 图片 / 视频批量下载入库（MinIO/OSS 当前仅预留）
- 爬虫 / 订阅 / 分析按 shop_id 关联回门店体系（当前按 user_id）
- 竞对博主对比分析
- **[规划中]** 订阅深度详情增量同步
- **[规划中]** 博主真实数据评分改造（C9，见上）

---

## 技术债（已登记）

1. 前端构建：`npm run build` 被 `ProfileEditorPage.test.tsx` 类型错误阻塞，暂用 `npx vite build`，需修复后恢复
2. 历史订阅数据：部分 `xhs_user_id` 截断导致刷新失败，需清洗 / 修复并加完整性校验
3. 多租户：当前 /crawl-jobs、/notes、/subscriptions 均按 user_id 隔离，未挂 shop_id；并入聚合前需补 shop 关联
4. MinIO/OSS：当前仅预留，爬虫图片走实时代理不落盘；批量下载入库时接入
5. SubscriptionScheduler：进程内 APScheduler 调度，服务重启后调度计划丢失，需接 Celery Beat 后解除
6. 采样估算精度（C7 现行方案）：`estimated` 笔记在博主发布节奏剧烈波动或存在异常点赞（刷量）场景可能偏差较大——这正是 C9 想解决的问题，C9 排期前暂无缓解手段

~~7. crawl_jobs.job_type 迁移~~ —— 已通过迁移 `a7b8c9d0e1f2` 完成，从技术债移除（见 C8）
