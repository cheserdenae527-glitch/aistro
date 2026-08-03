# M2 — Core Data Models & CRUD 设计文档

> **日期：** 2026-07-30
> **基于：** SPEC.md v0.1, M1 项目骨架

## 概述

在 M1 骨架的基础上，完成所有核心业务表的创建和基础 CRUD API，使后端具备完整的领域模型和可操作的数据入口。前端同步完成商家和门店的管理页面。

## 执行流水线

```
Step 0:  docker compose up -d postgres redis
Step 1:  写 8 个 Model 文件（models/merchant.py, shop.py, ...）
Step 2:  在 alembic/env.py 里 import 新增的 Model
Step 3:  alembic revision --autogenerate（连真实 PG 生成迁移）
Step 4:  人工检查生成的迁移文件（Enum、FK 是否完整）
Step 5:  alembic upgrade head
Step 6:  写 Schema + Router
Step 7:  写 seed.py
Step 8:  跑 seed 验证
Step 9:  写前端商家/门店页面
```

## Model 设计

所有模型继承 `app.core.database.Base`，使用 PostgreSQL 原生 UUID 主键和 timestamptz。

### 表依赖图（建表顺序）

```
merchants ──→ shops ──→ platform_shops
                  │         ├── reviews
                  │         └── menu_items
                  ├── crawl_jobs
                  ├── reports
                  └── manual_imports
```

### M2 包含的 8 张表

| # | 表 | 父表 | 说明 |
|---|-----|------|------|
| 1 | merchants | — | 商家 |
| 2 | shops | merchants | 门店 |
| 3 | platform_shops | shops | 各平台店铺绑定 |
| 4 | reviews | platform_shops | 评价 |
| 5 | menu_items | platform_shops | 菜品 |
| 6 | crawl_jobs | shops | 爬虫任务 |
| 7 | reports | shops | 报告 |
| 8 | manual_imports | shops | 手动导入 |

### 外键约束

| 子表 | 父表 | 外键列 | ON DELETE |
|------|------|--------|-----------|
| shops | merchants | merchant_id | CASCADE |
| platform_shops | shops | shop_id | CASCADE |
| reviews | platform_shops | platform_shop_id | CASCADE |
| menu_items | platform_shops | platform_shop_id | CASCADE |
| crawl_jobs | shops | shop_id | RESTRICT |
| reports | shops | shop_id | RESTRICT |
| manual_imports | shops | shop_id | RESTRICT |

外键全部定义在子表上。爬虫任务、报告、手动导入不做级联删除（保留历史记录）。

### 枚举类型命名表

| 表 | 字段 | Enum 类型名 | 值 |
|----|------|-------------|-----|
| merchants | tier | merchant_tier | trial, pro, enterprise |
| reviews | sentiment | review_sentiment | positive, neutral, negative |
| reviews | reply_status | review_reply_status | unreplied, ai_replied, manual_replied |
| crawl_jobs | status | crawl_job_status | pending, running, success, failed, cancelled |
| crawl_jobs | job_type | crawl_job_type | full, incremental |
| manual_imports | status | import_status | pending, parsed, imported, failed |
| manual_imports | import_type | import_type | reviews_csv, reviews_paste, menu_csv, shop_data |
| reports | type | report_type | weekly, daily, competitor |
| reports | status | report_status | draft, published |
| platform_shops | platform | platform_name | meituan, dianping, douyin, xiaohongshu, eleme |

Model 中所有 `sa.Enum(...)` 必须显式指定 `name=`（上表的值）和 `create_type=True`。

### 字段定义

严格对齐 SPEC.md §3.2，关键点：

- 所有 `id` 字段：`UUID PK, default=uuid.uuid4`
- 所有 `created_at`：`DateTime(timezone=True), server_default=sa.func.now()`
- 门店 `category`：普通 varchar（枚举值不由数据库约束）
- 平台 `platform`：`sa.Enum("meituan", "dianping", "douyin", "xiaohongshu", "eleme", name="platform_name", create_type=True)`

## API 路由设计

### 商家 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/merchants | 列表（支持 name 模糊搜索，分页） |
| POST | /api/v1/merchants | 创建 |
| GET | /api/v1/merchants/{mid} | 详情 |
| PATCH | /api/v1/merchants/{mid} | 更新 |
| DELETE | /api/v1/merchants/{mid} | 删除 |

### 门店 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/merchants/{mid}/shops | 按商家列出门店 |
| POST | /api/v1/merchants/{mid}/shops | 创建门店 |
| GET | /api/v1/shops/{sid} | 门店详情（扁平入口） |
| PATCH | /api/v1/shops/{sid} | 更新门店 |
| DELETE | /api/v1/shops/{sid} | 删除门店 |
| GET | /api/v1/shops/{sid}/platforms | 平台店铺列表（扁平入口） |
| POST | /api/v1/shops/{sid}/platforms | 绑定平台店铺 |

评价/菜单/爬虫/报告/导入的 API 留到对应 M3~M6。

## Schema 设计原则

- 每个 Model 对应三个 Schema：`Create`、`Update`（全部 optional）、`Response`（from_attributes=True）
- 列表响应分页：`{"items": [...], "total": N, "page": P, "size": S}`
- 枚举字段在 Pydantic 中复用 Model 的 Enum 类型值（字符串，不做额外映射）

## Seed 数据

`backend/scripts/seed.py`：

- 1 个用户（admin@test.com / admin123）
- 2 个商家（"川味坊火锅", "星巴克咖啡"）
- 每个商家 2-3 个门店
- 部分门店绑定 1-2 个平台店铺（美团/抖音）
- 少量示例评价

## 前端页面

- `/merchants` — merchants 列表页（Ant Design Table + 搜索 + 新建/编辑 Modal）
- `/merchants/:id` — 商家详情页（商家信息卡 + 门店 Table + 新建门店 Modal）
- 前端路由在现有 App.tsx 中追加

## 不包含在 M2 范围内

- 评价/菜单/爬虫/报告/导入的 API 和前端页面（评价 → M4，爬虫 → M5，导入 → M6，报告 → M7）
- 跨平台聚合计算（M3）
- 竞对分析（Phase 2）
- 菜单 AI 优化（Phase 2）

## 技术约束

- 所有新文件使用 PowerShell heredoc 写入，避免 apply_patch 空格问题
- 所有 FastAPI route handler 使用 async/await
- 所有 Schema 使用 Pydantic v2 model_validate
- 分页入参：page（从 1 起始，默认 1）和 size（默认 20，最大 100）

