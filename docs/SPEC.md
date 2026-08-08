 # AiRestro — 餐饮商家 AI 运营工作台 设计规约
 
 > 版本：v0.2 · 2026-08-07
 > 状态：迭代中可修正
 > 说明：爬虫管理板块的详细规约以 [SPEC-CRAWLER.md](./SPEC-CRAWLER.md) 为准
 
 ---
 
 ## 1. 项目定位
 
 **一句话**：面向中小餐饮商家代运营服务商的一站式 AI 数据聚合与运营工作台。
 
 **目标用户**：
 - 主要：代运营服务商团队（运营负责人、内容/评价专员、达人商务、投放专员）
 - 次要：有线上运营需求的单店/小连锁商家
 
 **核心价值**：把代运营 70% 的案头工作（数据聚合、竞对调研、评价管理、报告生成、内容辅助）交给 AI，让运营人员聚焦在真人需介入的决策和关系维护上。
 
 ---
 
 ## 2. 技术架构
 
 ### 2.1 整体架构图
 
 ```
 ┌─────────────────────────────────────────────────┐
 │              Frontend (React + TS)              │
 │  Ant Design 5 · React Router · Recharts         │
 └──────────────────────┬──────────────────────────┘
                        │ REST API（JSON）
 ┌──────────────────────┴──────────────────────────┐
 │            API Gateway — FastAPI                │
 │  · 鉴权中间件（JWT）  · 请求校验（Pydantic）     │
 │  · 限流 · CORS                                  │
 ├──────────────────────────────────────────────────┤
 │  Service Layer（业务服务）                        │
 │  ┌──────────┐ ┌────────┐ ┌──────────┐          │
 │  │聚合服务   │ │评价服务 │ │商家服务   │          │
 │  │AggService │ │Review  │ │Merchant  │          │
 │  └──────────┘ └────────┘ └──────────┘          │
 │  ┌──────────┐ ┌────────┐ ┌──────────┐          │
 │  │报告服务   │ │导入服务 │ │任务调度   │          │
 │  │Report    │ │Import  │ │Scheduler │          │
 │  └──────────┘ └────────┘ └──────────┘          │
 ├──────────────────────────────────────────────────┤
 │  AI Service Layer                                │
 │  · LLM 文案生成（OpenAI / 国产模型）             │
 │  · 情感分析 / 关键词提取                        │
 │  · 商圈诊断引擎 · 策略推荐                      │
 ├──────────────────────────────────────────────────┤
 │  Data Layer                                      │
 │  · PostgreSQL（业务数据）                        │
 │  · Redis（缓存 + 任务队列）                      │
 │  · MinIO/S3（图片/附件存储）                    │
 └──────────────────────────────────────────────────┘
 ```
 
 ### 2.2 技术选型明细
 
 | 层 | 技术 | 选型理由 |
 |---|---|---|
 | **前端框架** | React + TypeScript 18 | 生态最成熟 |
 | **UI 组件库** | Ant Design 5 | 企业级后台首选 |
 | **图表** | Recharts | React 原生，轻量 |
 | **后端框架** | FastAPI | Python 异步 API，Pydantic 校验 |
 | **ORM** | SQLAlchemy 2.0 + Alembic | 异步支持，迁移管理 |
 | **数据库** | PostgreSQL 16 | JSON 字段，全文检索 |
 | **缓存/队列** | Redis + Celery | 任务调度，定时爬虫 |
 | **对象存储** | MinIO / 阿里云 OSS | 图片和附件存储；爬虫快照为预留能力，当前爬虫暂未使用 |
 | **AI 模型** | OpenAI GPT-4o / 国产模型切换 | 按成本和合规切换 |
 | **部署** | Docker Compose | 环境一致 |
 | **认证** | JWT + OAuth2 | FastAPI 原生支持 |
 
 ### 2.3 技术约束与原则
 
 - **前后端分离**：纯 REST API，不混模板渲染
 - **异步优先**：FastAPI async handler + async ORM
 - **爬虫与业务解耦**：爬虫产出的原始数据进 raw_json 字段，聚合后再存入结构化字段
 - **AI 可插拔**：AI Service 层通过抽象接口调用，可切换模型厂商
 - **多租户设计**：一个服务商账号管理多个商家，商家数据严格隔离
 
 ---
 
 ## 3. 数据模型
 
 ### 3.1 核心实体关系
 
 ```
 User (服务商账号) 1 ── N Merchant (商家)
 User 1 ── N Subscription (小红书博主订阅，按用户隔离；暂未挂 shop_id)
 Merchant 1 ── N Shop (门店)
 Shop 1 ── N PlatformShop (各平台店铺绑定)
 Shop 1 ── N Review (评价)
 Shop 1 ── N MenuItem (菜品)
 Shop 1 ── N CompetitorAnalysis (竞对分析)
 Shop 1 ── N CrawlJob (爬虫任务)
 Shop 1 ── N Report (报告)
 ```
 
 ### 3.2 关键表结构
 
 #### users
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | email | varchar(255) UNIQUE | 登录邮箱 |
 | password_hash | varchar(255) | bcrypt 哈希 |
 | name | varchar(100) | 姓名/团队名 |
 | role | enum admin/operator | 角色 |
 | created_at | timestamptz | |
 
 #### merchants
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | user_id | UUID FK users | 所属服务商 |
 | name | varchar(200) | 商家名称 |
 | contact_name | varchar(100) | 联系人 |
 | contact_phone | varchar(20) | |
 | tier | enum trial/pro/enterprise | 套餐等级 |
 | notes | text | 备注 |
 | created_at | timestamptz | |
 
 #### shops
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | merchant_id | UUID FK merchants | |
 | name | varchar(200) | 门店名称 |
 | address | text | |
 | phone | varchar(20) | |
 | category | varchar(50) | 品类（火锅/烧烤/快餐/咖啡） |
 | status | enum active/inactive | |
 | created_at | timestamptz | |
 
 #### platform_shops
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | shop_id | UUID FK shops | |
 | platform | enum meituan/dianping/douyin/xiaohongshu/eleme | |
 | platform_shop_id | varchar(100) | 平台上的店铺 ID |
 | shop_url | text | 店铺链接 |
 | shop_name | varchar(200) | 平台上的店名 |
 | rating | decimal(2,1) | 评分 |
 | monthly_sales | int | 月售 |
 | total_reviews | int | 累计评价数 |
 | raw_json | jsonb | 爬虫原始数据快照 |
 | last_synced_at | timestamptz | 最后同步时间 |
 | created_at | timestamptz | |
 
 #### reviews
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | platform_shop_id | UUID FK platform_shops | |
 | platform_review_id | varchar(100) | 平台评价 ID（去重） |
 | reviewer_name | varchar(100) | |
 | rating | smallint | 1-5 分 |
 | content | text | 评价内容 |
 | tags | jsonb | AI 提取关键词 |
 | sentiment | enum positive/neutral/negative | AI 情感分类 |
 | reply_status | enum unreplied/ai_replied/manual_replied | |
 | ai_reply | text | AI 生成的回复草稿 |
 | reply_content | text | 实际回复内容 |
 | replied_at | timestamptz | |
 | reviewed_at | timestamptz | 评价时间 |
 | created_at | timestamptz | |
 
 #### menu_items
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | platform_shop_id | UUID FK platform_shops | |
 | name | varchar(200) | 菜品名 |
 | category | varchar(50) | 分类 |
 | price | decimal(10,2) | 价格 |
 | original_price | decimal(10,2) | 原价 |
 | sales_count | int | 月销量 |
 | description | text | 描述 |
 | image_url | text | 图片链接 |
 | ai_optimized_name | text | AI 建议的名称 |
 | ai_optimized_desc | text | AI 建议的描述 |
 | is_recommended | boolean | 是否推荐菜 |
 | created_at | timestamptz | |
 
 #### crawl_jobs
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | shop_id | UUID FK shops | |
 | platform | enum | 爬取目标平台 |
 | job_type | enum search/note_detail/comment | 已通过迁移 a7b8c9d0e1f2 从历史枚举 full/incremental 迁移完成 |
 | status | enum pending/running/success/failed/cancelled | |
 | schedule | varchar(50) | cron 或 manual |
 | result_summary | jsonb | 结果统计 |
 | error_log | text | 错误日志 |
 | started_at | timestamptz | |
 | finished_at | timestamptz | |
 | created_at | timestamptz | |
 

#### subscriptions

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK users | 所属服务商（当前按用户隔离，未挂 shop_id） |
| xhs_user_id | varchar(100) | 小红书博主 ID（来自搜索接口 id，需完整保存） |
| nickname | varchar(100) | 博主昵称 |
| avatar | text | 头像 URL |
| note_count | int | 笔记数快照 |
| follower_count | int | 粉丝数快照 |
| following_count | int | 关注数快照 |
| notified_note_count | int | 上次"有更新"提醒时的笔记数快照 |
| last_crawled_at | timestamptz | 最后轻量快照刷新时间 |
| created_at | timestamptz | |

> `last_deep_synced_at` 字段**尚未加入表结构**——"深度详情增量同步"是规划中功能，见 SPEC-CRAWLER.md §11.6。

#### subscription_snapshots

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| subscription_id | UUID FK subscriptions | |
| note_count | int | |
| follower_count | int | |
| following_count | int | |
| crawled_at | timestamptz | |

> `note_details`（笔记详情快照缓存）、`blogger_analysis_tasks`（博主分析任务）两张表是"真实数据版评分改造"设计方案的一部分，**尚未建表**，字段草案见 [SPEC-CRAWLER.md](./SPEC-CRAWLER.md) §3.3-3.4、§11。

 #### competitor_analyses
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | shop_id | UUID FK shops | |
 | competitor_shop_id | UUID FK platform_shops | |
 | analysis_report | jsonb | AI 生成的对比分析 |
 | distance_m | int | 距离（米） |
 | price_level | enum lower/similar/higher | 价格带对比 |
 | created_at | timestamptz | |
 
 #### reports
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | shop_id | UUID FK shops | |
 | type | enum weekly/daily/competitor | |
 | title | varchar(200) | |
 | content | jsonb | AI 报告内容 |
 | status | enum draft/published | |
 | created_at | timestamptz | |
 
 #### manual_imports
 
 | 字段 | 类型 | 说明 |
 |---|---|---|
 | id | UUID PK | |
 | shop_id | UUID FK shops | |
 | import_type | enum reviews_csv/reviews_paste/menu_csv/shop_data | |
 | source_data | text | 原始输入 |
 | parsed_result | jsonb | 解析后的结构化数据 |
 | status | enum pending/parsed/imported/failed | |
 | error_message | text | |
 | created_at | timestamptz | |
 
 ---
 
 ## 4. MVP 页面与路由
 
 | 路由 | 页面 |
 |---|---|
 | /login | 登录 |
 | / | Dashboard 总看板 |
 | /merchants | 商家列表 |
 | /shops/:id | 门店详情（聚合数据） |
 | /shops/:id/reviews | 评价管理 |
 | /crawl | 爬虫管理（任务 / 搜索 / 作品 / 浏览 / 分析 / 订阅） |
 | /data/import | 手动导入 |
 | /reports | 报告中心 |
 | /reports/:id | 报告详情 |
 | /settings | 系统设置 |
 
 ### 4.1 Dashboard 组件树
 
 ```
 DashboardPage
 ├─ MerchantSwitcher（商家选择器，顶部）
 ├─ StatsCardRow（曝光/评分/评价数/月售 四张卡）
 ├─ RecentReviewsPanel（最新评价动态 + 差评标记）
 ├─ PlatformSummaryTabs（按平台切换数据概览）
 ├─ CrawlStatusCard（爬虫同步状态）
 └─ QuickActions（手动导入 / 立即同步按钮）
 ```
 
 ### 4.2 门店详情组件树
 
 ```
 ShopsDetailPage
 ├─ ShopHeader（店名/地址/品类 + 编辑按钮）
 ├─ PlatformDataTabs（美团 | 抖音 | 小红书 | 饿了么）
 │   └─ PlatformShopCard（评分/月售/评价数）
 ├─ ReviewManagementPanel
 │   ├─ ReviewFilter（评分/平台/时间/情感过滤）
 │   ├─ ReviewTable（评价列表 + AI 回复列）
 │   ├─ ReplyDrawer（AI 生成回复 + 编辑 + 确认）
 │   └─ ReviewAnalyticsCard（差评关键词云）
 └─ CrossPlatformCompare（跨平台数据对比）
 ```
 
 ### 4.3 爬虫管理组件树（/crawl）

```
CrawlJobsPage
├─ Tab 任务列表
│   ├─ SearchBar（关键词 + 排序/类型/时间/条数 + 历史记录）
│   ├─ ProgressBar + CrawlTaskTable（3 秒轮询）
│   └─ NewCrawlModal（search / note_detail / comment）
├─ Tab 搜索博主
│   ├─ UserSearchBar（昵称 + 深度分析条数 0/10/20/50）
│   └─ UserCard（查看作品 / 分析 / 订阅）
├─ Tab 博主作品（NoteCard 网格，点击打开详情）
├─ Tab 浏览结果（点赞/评论/收藏排序 + 保存/加载历史）
├─ Tab 博主分析（UserAnalysisPanel：统计卡 + 折线/雷达/柱状图 + 洞察 + 笔记表）
└─ Tab 博主订阅（SubscriptionsPage 表格）
```

---
## 5. API 设计（关键接口）
 
 ### 5.1 聚合数据
 
 GET  /api/v1/shops/{id}/aggregated -> 各平台聚合指标
 GET  /api/v1/shops/{id}/trends?period=7d|30d -> 趋势数据
 
 ### 5.2 评价管理
 
 GET    /api/v1/shops/{id}/reviews 分页/筛选
 POST   /api/v1/shops/{id}/reviews/{rid}/ai-reply  生成回复
 PUT    /api/v1/shops/{id}/reviews/{rid}/reply     确认回复
 GET    /api/v1/shops/{id}/reviews/analytics        关键词/情感分布
 
 ### 5.3 爬虫管理

```
POST   /api/v1/crawl-jobs                    创建任务（search / note_detail / comment）
GET    /api/v1/crawl-jobs                    任务列表
GET    /api/v1/crawl-jobs/{job_id}           任务详情

POST   /api/v1/notes/search-users            搜索博主
POST   /api/v1/notes/search                  搜索笔记
GET    /api/v1/notes/{note_id}               笔记详情
GET    /api/v1/notes/{note_id}/comments      笔记评论
GET    /api/v1/notes/users/{user_id}/notes   按博主 ID 取作品列表
POST   /api/v1/notes/users/{user_id}/analysis  博主数据分析评分（现状：同步接口，分层抽样估算版，保留兼容）
POST   /api/v1/notes/users/{user_id}/analysis-tasks         创建博主分析任务（真实数据版，异步）
GET    /api/v1/notes/users/{user_id}/analysis-tasks/{id}   查询分析任务进度/结果
DELETE /api/v1/notes/users/{user_id}/analysis-tasks/{id}   取消分析任务

POST   /api/v1/subscriptions                 订阅博主
GET    /api/v1/subscriptions                 订阅列表
POST   /api/v1/subscriptions/{id}/refresh    刷新订阅数据（现状：仅轻量快照，不抓详情）
GET    /api/v1/subscriptions/{id}/notes      订阅博主笔记
GET    /api/v1/subscriptions/{id}/snapshots  订阅快照
DELETE /api/v1/subscriptions/{id}            取消订阅

GET    /api/v1/images/proxy?url=&size=       图片代理 / 高清放大
GET    /api/v1/images/video-proxy?url=       视频代理播放 / 下载
```

> 博主分析详细字段、评分口径以 [SPEC-CRAWLER.md](./SPEC-CRAWLER.md) §5 为准（现状），§11 为"真实数据版评分改造"设计方案（**规划中，未开发**），此处仅列现状接口概览，不含规划中的异步任务接口。
### 5.4 手动导入
 
 POST   /api/v1/shops/{id}/imports/preview   解析预览
 POST   /api/v1/shops/{id}/imports/{id}/confirm  确认导入
 
 ### 5.5 报告
 
 POST   /api/v1/shops/{id}/reports/generate?type=weekly
 GET    /api/v1/shops/{id}/reports
 
 ---
 
 ## 6. 爬虫集成策略

- 爬虫代码独立于主业务代码，放在 `services/crawler/` 目录，当前小红书实现位于 `services/crawler/xhs/`
- `XhsCrawler` 封装 Spider_XHS 运行时，统一接口：search_notes / search_users / get_user_info / get_user_notes / get_note_detail / get_comments / check_cookie
- 防风控：随机延时 + 指数退避 + 代理池轮换 + Cookie 健康检测 + 失败重试
- 任务运行器当前为 threading 内存任务（`crawler/tasks.py`），预留 Redis/Celery 替换点
- 爬虫产出原始 JSON -> `processor.normalize_*` 标准化 -> 供浏览 / 订阅 / 分析使用
- 博主分析评分引擎为独立纯函数模块 `app/services/xhs_analysis.py`
- 详细规约见 [SPEC-CRAWLER.md](./SPEC-CRAWLER.md)；手工导入为后续迭代

---
## 7. AI 能力清单（Phase 1）
 
 | 能力 | 输入 | 输出 | 技术方案 |
 |---|---|---|---|
 | 评价回复生成 | 评价内容+评分+商家信息 | 回复文本 | LLM prompt |
 | 差评关键词提取 | 评价列表 | 关键词云 | LLM+NLP |
 | 情感分类 | 评价内容 | positive/neutral/negative | LLM |
 | 周报生成 | 7天数据聚合 | 结构化报告 | LLM+数据模板 |
 | 商圈诊断 | 竞对数据 | 诊断报告 | LLM 对比分析 |
 | 菜品名优化 | 原名+分类 | 优化建议 | LLM |
 | 菜单描述优化 | 菜品信息 | 优化描述 | LLM |
 
 ---
 
 ## 8. 目录结构
 
 aistro/
   backend/
     app/
       api/v1/          路由层（notes / subscriptions / crawl-jobs / images）
       models/          SQLAlchemy 模型
       schemas/         Pydantic 校验
       services/        业务逻辑（含 xhs_analysis 评分引擎）
       core/            配置/安全/数据库
       main.py
     services/
       crawler/         爬虫基类 + XHS 实现（xhs/）+ processor
     alembic/          数据库迁移
     requirements.txt
     Dockerfile
   frontend/
     src/
       pages/           Dashboard/Shops/CrawlJobs/Subscriptions/Reputation/Studio...
       components/      通用组件（NoteCard/NoteDetail/UserAnalysisPanel）
       hooks/
       services/        API 调用
       store/           状态管理
       App.tsx
     package.json
     Dockerfile
   docker-compose.yml
   docs/SPEC.md
   docs/SPEC-CRAWLER.md
   docs/PLAN.md
   docs/PLAN-CRAWLER.md
   README.md
 
 ---
 
 ## 9. Phase 1 MVP 边界
 
 ### 包含
 - 商家管理（增删改查 + 多商家切换）
 - 多平台数据聚合展示（美团/抖音/小红书）
 - 评价管理（展示 + 筛选 + AI 回复生成 + 关键词分析）
 - 小红书爬虫管理：任务 / 搜索 / 博主作品 / 订阅 / 博主分析评分
 - 手动导入（CSV/粘贴 + 预解析）
 - AI 自动周报生成
 - 用户认证（JWT）
 
 ### 不包含
 - 菜单 AI 优化（Phase 2）
 - 竞对自动分析 + 商圈诊断（Phase 2）
 - 达人库管理（Phase 2）
 - 内容工坊（Phase 2）
 - 投放效果分析（Phase 3）
 - 多成员协作
 - 移动端适配
 
 ---
 
 ## 10. 开发规范
 
 - 分支策略：main -> dev -> feature/xxx
 - 提交规范：feat: / fix: / docs: / refactor: 前缀
 - 代码风格：Python Black+Ruff，TS ESLint+Prettier
 - 测试：pytest（后端）+ Vitest（前端）
 - API 文档：FastAPI 自动 OpenAPI + Swagger UI
