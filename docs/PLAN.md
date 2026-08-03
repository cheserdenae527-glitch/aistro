 # AiRestro 实现计划
 
 > 基于 SPEC v0.1 · 按依赖顺序排列
 
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
 
 1. Alembic 迁移：所有表（merchants / shops / platform_shops / reviews / menu_items / crawl_jobs / reports / manual_imports）
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
 
 **目标**：爬虫调度框架 + 手动触发的爬虫任务。
 
 ```
 前置：M2
 工作量：1 次对话（爬虫框架 + 1 个平台 demo）
 ```
 
 ### 任务清单
 
 1. 爬虫基类 BaseCrawler 定义 + 统一接口
 2. 美团爬虫 Demo（集成 GitHub 开源项目）
 3. Celery worker + 任务调度
 4. 爬虫任务创建 / 触发 / 日志查看 API
 5. 前端爬虫管理页（任务列表 + 创建 + 日志）
 6. Data Processor：爬虫原始 JSON 清洗入库
 
 ### 交付物
 - 可配置并触发美团数据爬取
 - 爬取结果自动存入 platform_shops 和 reviews
 - 前端可查看任务状态和日志
 
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
