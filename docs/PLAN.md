 # AiRestro 实现计划
 
 > 基于 SPEC v0.2 · 按依赖顺序排列
 
 ## 执行策略
 
 每个里程碑启动一个独立对话（分支线程），完成后合并回主分支。
 总设计师（本线程）只负责框架、接口契约、边界检查。
 
 ---
 
 ## M1 — Project Scaffold（项目骨架）
 
 **目标**：可运行的项目框架，Docker Compose 一键启动。
 
 ```
 前置：无
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. 初始化 backend/：FastAPI 项目结构、main.py、config、database 连接
 2. 初始化 frontend/：React + TS + Ant Design 5 脚手架
 3. Docker Compose：PostgreSQL 16 + Redis + MinIO + backend + frontend
 4. 用户认证：users 表、JWT 登录/注册 API、前端登录页
 5. Alembic 初始化 + users 表迁移
 
 ### 交付物
 - curl localhost:8000/docs 可访问 Swagger
 - 前端 localhost:3000 显示登录页
 - docker-compose up 一键启动所有服务
 
 ---
 
 ## M2 — Core Data Models + CRUD（数据模型与基础 API）
 
 **目标**：所有核心表的迁移 + 基础增删改查 API。
 
 ```
 前置：M1
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. Alembic 迁移：所有表（merchants / shops / platform_shops / reviews / menu_items / crawl_jobs / reports / manual_imports / competitor_analyses）
    - subscriptions / subscription_snapshots 由 M5 爬虫板块补建，已完成（见 PLAN-CRAWLER.md）
   - [规划中] note_details / blogger_analysis_tasks 为 M5 真实数据评分改造（C9）设计方案的一部分，尚未建表
 2. 后端 CRUD API：
    - 商家管理（增删改查 + 多商家切换）
    - 门店管理（增删改查）
    - 平台店铺绑定
 3. 前端商家列表页 + 商家表单
 4. 前端门店列表页 + 门店表单
 5. 基础数据 Seed 脚本（假数据用于开发）
 
 ### 交付物
 - Postman/curl 可操作所有 CRUD
 - 前端可添加商家、添加门店、查看列表
 
 ---
 
 ## M3 — Data Aggregation Dashboard（数据聚合仪表盘）
 
 **目标**：Dashboard + 门店详情页展示聚合数据。
 
 ```
 前置：M2
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. 后端聚合 API：
    - GET /api/v1/shops/{id}/aggregated -> 跨平台数据聚合
    - GET /api/v1/shops/{id}/trends -> 趋势数据
 2. 前端 Dashboard 页面（商家切换器 + 统计卡片 + 评价动态 + 爬虫状态）
 3. 前端门店详情页（平台数据 Tabs + 跨平台对比）
 
 ### 交付物
 - Dashboard 展示多门店概览 + 核心指标
 - 门店详情页可切换平台查看数据
 
 ---
 
 ## M4 — Review Management（评价管理）
 
 **目标**：评价展示 / 筛选 / AI 回复 / 差评分析。
 
 ```
 前置：M2（需要 reviews 表）
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. 后端评价 API（列表 / 筛选 / 情感分类 / 关键词提取 / AI 回复生成）
 2. AI Service 抽象层 + OpenAI 实现（评价回复生成 + 情感分类 + 关键词提取）
 3. 前端评价管理页（评价表格 + 筛选器 + 回复抽屉 + 关键词云）
 4. 评价回复状态流转（unreplied -> ai_replied -> manual_replied）
 
 ### 交付物
 - 评价列表可按评分/平台/情感筛选
 - 点击评价可 AI 生成回复，编辑后确认
 - 差评关键词云展示
 
 ---
 
 ## M5 — Crawler Integration（爬虫集成与调度）

**目标**：小红书爬虫管理 + 博主运营数据分析。基础版已交付并线上运行，详细见 [PLAN-CRAWLER.md](./PLAN-CRAWLER.md)。
**状态说明**：本节严格区分"已交付"（代码已写、可运行）与"规划中"（方案已设计、未写代码）。此前版本曾把规划方案误标为已交付，本版订正，以 PLAN-CRAWLER.md 的 C1-C9 编号为准。

```
前置：M2
工作量：基础版已交付，按板块文档持续迭代
```

### 已交付任务

1. 爬虫基类 BaseCrawler + CrawlResult 统一接口
2. XhsCrawler 封装 Spider_XHS 运行时：
   - 搜索笔记 / 搜索博主 / 用户信息 / 用户作品 / 笔记详情 / 评论 / Cookie 检测
   - 防风控：随机延时 + 指数退避 + 代理池轮换 + 失败重试
3. 爬虫任务运行器（threading 内存任务，预留 Redis/Celery）：search / note_detail / comment
4. 爬虫任务 API：创建 / 列表 / 详情
5. Data Processor：normalize_note / normalize_comment / normalize_user + 计数解析 + published_at
6. 笔记浏览 API（含 `GET /notes/users/{user_id}/notes` 按博主取作品）+ 图片/视频代理 + 前端浏览结果页（筛选排序 / 浏览历史）
7. 博主搜索 / 作品 / 订阅（subscriptions + snapshots）
8. **博主分析评分引擎（分层抽样估算版）**：当前线上运行的唯一评分实现，同步接口 `POST /notes/users/{user_id}/analysis`（见 PLAN-CRAWLER.md C7）
9. 全局订阅按钮（博主卡片 / 作品与浏览列表 / 笔记详情 / 分析页头复用组件）+ 批量订阅状态查询 + 订阅**轻量快照**定时刷新与更新提醒（APScheduler，见 PLAN-CRAWLER.md C6）
10. `crawl_jobs.job_type` 迁移为 search/note_detail/comment（见 PLAN-CRAWLER.md C8）

### 规划中（设计已定，尚未开发——不计入已交付）

- **博主真实数据评分改造**（PLAN-CRAWLER.md C9）：两段式筛选、五维评分仅消费真实样本、覆盖率可信度、异常识别、后台分析任务（异步 + 进度可见）、详情快照缓存、订阅深度详情增量同步。原始设计稿 `docs/DESIGN-BLOGGER-SCORING-REALDATA.md`，该文档明确写"方案稿，尚未改代码"，PLAN-CRAWLER.md C9 是权威的实现状态跟踪。

### 待迭代

- 美团 / 抖音 / 大众点评爬虫
- Redis/Celery 持久化任务队列
- 通用爬虫任务定时化调度（crawl_jobs 搜索/详情任务按 cron 自动执行）——仅订阅轻量刷新已实现定时化
- 图片 / 视频批量下载入库（MinIO/OSS 当前仅预留，未接入爬虫）
- 多平台数据统一写入 platform_shops / reviews
- 爬虫 / 订阅 / 分析按 shop_id 关联回门店体系（当前按 user_id）
- 博主真实数据评分改造（见上"规划中"，排期后从此处移除并标注开发中）

### 技术债（已登记）

- `npm run build` 被 `ProfileEditorPage.test.tsx` 类型错误阻塞，暂用 `npx vite build`，需修复后恢复
- 历史订阅数据存在截断 `xhs_user_id`，需清洗 / 修复并加完整性校验
- SubscriptionScheduler 为进程内 APScheduler 调度，服务重启后调度计划丢失，需接 Celery Beat 后解除
- 采样估算精度（当前线上唯一评分方案）：`estimated` 笔记在博主发布节奏剧烈波动或存在异常点赞（刷量）场景可能偏差较大；缓解方案即"规划中"的真实数据版改造，尚未排期

### 交付物

- 真实小红书博主 242 篇作品完成抓取与评分（已验证，评分方式为分层抽样估算版）
- 前端 `/crawl` 全流程可用：任务 / 搜索 / 作品 / 浏览 / 分析（同步接口）/ 订阅

---

## M6 — Manual Import（手动导入）
 
 **目标**：CSV/粘贴导入数据，AI 辅助解析。
 
 ```
 前置：M2
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. 后端导入 API（上传 / 粘贴 / 预览解析 / 确认导入）
 2. CSV/Excel 解析引擎（pandas + openpyxl）
 3. AI 辅助文本解析（粘贴的无格式文本 -> 结构化数据）
 4. 前端导入页面（类型选择 + 上传/粘贴 + 预览 + 确认）
 
 ### 交付物
 - 上传评价 CSV 后可预览解析结果并导入
 - 粘贴文本可 AI 解析为结构化数据
 
 ---
 
 ## M7 — AI Weekly Report（自动周报）
 
 **目标**：基于 7 天聚合数据，自动生成 AI 周报。
 
 ```
 前置：M3 + M4（需要数据+评价）
 工作量：1 次对话
 ```
 
 ### 任务清单
 
 1. 后端报告生成 API（按门店生成周报）
 2. AI 周报 Agent（LLM 分析趋势/问题/建议）
 3. 前端报告中心页 + 报告详情页
 4. 定时周报生成任务（Celery Beat）
 
 ### 交付物
 - 一键生成门店周报（含数据趋势+评价分析+建议）
 - 报告中心可查看历史报告
 
 ---
 
 ## 里程碑依赖图
 
 ```
 M1 脚手架
  │
  ├──→ M2 数据模型+CRUD  ←── 所有模块的基石
  │      │
  │      ├──→ M3 Dashboard+聚合数据
  │      │         │
  │      │         └──→ M7 AI 周报
  │      │
  │      ├──→ M4 评价管理  ←── AI 第一块落地
  │      │
  │      ├──→ M5 爬虫集成
  │      │
  │      └──→ M6 手动导入
 ```
 
 ---
 
 ## 建议执行顺序
 
 1. **M1** → **M2**（先打地基）
 2. **M5 + M6 并行**（爬虫和导入互不依赖，都依赖 M2）
 3. **M3 + M4 并行**（Dashboard 和评价管理可同步进行）
 4. **M7**（依赖 M3+M4，放最后）
 
 每个里程碑内部，如果任务量超过一次对话的承载，可以再拆成子任务独立线程。
