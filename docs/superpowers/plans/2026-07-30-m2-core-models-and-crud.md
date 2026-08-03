# M2 — Core Data Models & CRUD 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 完成 8 张核心业务表的创建、基础 CRUD API、前端商家/门店管理页面，以及开发种子数据。

**架构：** 按层批量推进——先 Write All Models → 再迁移 → 再 All Schema + Router → Seed → 前端。外键 CASCADE 设计见设计文档，枚举命名统一用命名表。

**Tech Stack:** FastAPI async + SQLAlchemy 2.0 async + Pydantic v2 + Alembic + PostgreSQL 16 + Ant Design 5

---

### Task 0: 启动基础设施

**Files:** 无代码变更

- [ ] **Step 0.1: 启动 PostgreSQL**

  ```bash
  cd D:\two
  docker compose up -d postgres redis
  ```

  预期：PostgreSQL 在 localhost:5432 可用，Redis 在 localhost:6379 可用。

---

### Task 1: 写所有 8 个 Model 文件

**Files:**
- Create: `D:\two\backend\app\models\merchant.py`
- Create: `D:\two\backend\app\models\shop.py`
- Create: `D:\two\backend\app\models\platform_shop.py`
- Create: `D:\two\backend\app\models\review.py`
- Create: `D:\two\backend\app\models\menu_item.py`
- Create: `D:\two\backend\app\models\crawl_job.py`
- Create: `D:\two\backend\app\models\report.py`
- Create: `D:\two\backend\app\models\manual_import.py`

使用 PowerShell heredoc 写入每个文件。枚举全部使用命名表中的 `name=` + `create_type=True`。外键列名和引用表严格对照设计文档的外键约束表。

- [ ] **Step 1.1: 创建 models/merchant.py**

  ```python
  """商家模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class Merchant(Base):
      __tablename__ = "merchants"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
      name: Mapped[str] = mapped_column(String(200), nullable=False)
      contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
      contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
      tier: Mapped[str] = mapped_column(
          Enum("trial", "pro", "enterprise", name="merchant_tier", create_type=True),
          nullable=False,
          server_default="trial",
      )
      notes: Mapped[str | None] = mapped_column(Text, nullable=True)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

  > 注意：顶部需要 `import sqlalchemy as sa`。

- [ ] **Step 1.2: 创建 models/shop.py**

  ```python
  """门店模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class Shop(Base):
      __tablename__ = "shops"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      merchant_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
      )
      name: Mapped[str] = mapped_column(String(200), nullable=False)
      address: Mapped[str | None] = mapped_column(Text, nullable=True)
      phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
      category: Mapped[str | None] = mapped_column(String(50), nullable=True)
      status: Mapped[str] = mapped_column(
          String(20),
          nullable=False,
          server_default="active",
      )
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )

  ```

  models/__init__.py 需要统一 export：`from app.models.merchant import Merchant` 等。

- [ ] **Step 1.3: 创建 models/platform_shop.py**

  ```python
  """平台店铺绑定模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
  from sqlalchemy.dialects.postgresql import UUID, JSONB
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class PlatformShop(Base):
      __tablename__ = "platform_shops"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
      )
      platform: Mapped[str] = mapped_column(
          Enum("meituan", "dianping", "douyin", "xiaohongshu", "eleme",
               name="platform_name", create_type=True),
          nullable=False,
      )
      platform_shop_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
      shop_url: Mapped[str | None] = mapped_column(Text, nullable=True)
      shop_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
      rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
      monthly_sales: Mapped[int | None] = mapped_column(Integer, nullable=True)
      total_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
      raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.4: 创建 models/review.py**

  ```python
  """评价模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, SmallInteger, String, Text, String
  from sqlalchemy.dialects.postgresql import UUID, JSONB
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class Review(Base):
      __tablename__ = "reviews"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      platform_shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False
      )
      platform_review_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
      reviewer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
      rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
      content: Mapped[str | None] = mapped_column(Text, nullable=True)
      tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      sentiment: Mapped[str | None] = mapped_column(
          Enum("positive", "neutral", "negative", name="review_sentiment", create_type=True),
          nullable=True,
      )
      reply_status: Mapped[str] = mapped_column(
          Enum("unreplied", "ai_replied", "manual_replied",
               name="review_reply_status", create_type=True),
          nullable=False,
          server_default="unreplied",
      )
      ai_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
      reply_content: Mapped[str | None] = mapped_column(Text, nullable=True)
      replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.5: 创建 models/menu_item.py**

  ```python
  """菜品模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class MenuItem(Base):
      __tablename__ = "menu_items"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      platform_shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("platform_shops.id", ondelete="CASCADE"), nullable=False
      )
      name: Mapped[str] = mapped_column(String(200), nullable=False)
      category: Mapped[str | None] = mapped_column(String(50), nullable=True)
      price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
      original_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
      sales_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
      description: Mapped[str | None] = mapped_column(Text, nullable=True)
      image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
      ai_optimized_name: Mapped[str | None] = mapped_column(Text, nullable=True)
      ai_optimized_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
      is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.6: 创建 models/crawl_job.py**

  ```python
  """爬虫任务模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
  from sqlalchemy.dialects.postgresql import UUID, JSONB
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class CrawlJob(Base):
      __tablename__ = "crawl_jobs"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False
      )
      platform: Mapped[str] = mapped_column(
          Enum("meituan", "dianping", "douyin", "xiaohongshu", "eleme",
               name="platform_name", create_type=True),
          nullable=False,
      )
      job_type: Mapped[str] = mapped_column(
          Enum("full", "incremental", name="crawl_job_type", create_type=True),
          nullable=False,
          server_default="full",
      )
      status: Mapped[str] = mapped_column(
          Enum("pending", "running", "success", "failed", "cancelled",
               name="crawl_job_status", create_type=True),
          nullable=False,
          server_default="pending",
      )
      schedule: Mapped[str | None] = mapped_column(String(50), nullable=True)
      result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
      started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.7: 创建 models/report.py**

  ```python
  """报告模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, String
  from sqlalchemy.dialects.postgresql import UUID, JSONB
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class Report(Base):
      __tablename__ = "reports"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False
      )
      type: Mapped[str] = mapped_column(
          Enum("weekly", "daily", "competitor", name="report_type", create_type=True),
          nullable=False,
      )
      title: Mapped[str] = mapped_column(String(200), nullable=False)
      content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      status: Mapped[str] = mapped_column(
          Enum("draft", "published", name="report_status", create_type=True),
          nullable=False,
          server_default="draft",
      )
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.8: 创建 models/manual_import.py**

  ```python
  """手动导入模型。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import DateTime, Enum, ForeignKey, Text
  from sqlalchemy.dialects.postgresql import UUID, JSONB
  from sqlalchemy.orm import Mapped, mapped_column

  from app.core.database import Base
import sqlalchemy as sa


  class ManualImport(Base):
      __tablename__ = "manual_imports"

      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      shop_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False
      )
      import_type: Mapped[str] = mapped_column(
          Enum("reviews_csv", "reviews_paste", "menu_csv", "shop_data",
               name="import_type", create_type=True),
          nullable=False,
      )
      source_data: Mapped[str | None] = mapped_column(Text, nullable=True)
      parsed_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      status: Mapped[str] = mapped_column(
          Enum("pending", "parsed", "imported", "failed", name="import_status", create_type=True),
          nullable=False,
          server_default="pending",
      )
      error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=sa.func.now()
      )
  ```

- [ ] **Step 1.9: 更新 models/__init__.py**

  ```python
  from app.models.user import User
  from app.models.merchant import Merchant
  from app.models.shop import Shop
  from app.models.platform_shop import PlatformShop
  from app.models.review import Review
  from app.models.menu_item import MenuItem
  from app.models.crawl_job import CrawlJob
  from app.models.report import Report
  from app.models.manual_import import ManualImport

  __all__ = [
      "User", "Merchant", "Shop", "PlatformShop", "Review",
      "MenuItem", "CrawlJob", "Report", "ManualImport",
  ]
  ```

---

### Task 2: 更新 alembic/env.py 导入所有新 Model

**Files:**
- Modify: `D:\two\backend\alembic\env.py`

- [ ] **Step 2.1: 替换 import 行**

  原：
  ```python
  from app.models.user import User  # noqa: F401
  ```
  改为：
  ```python
  from app.models import User, Merchant, Shop, PlatformShop, Review, MenuItem, CrawlJob, Report, ManualImport  # noqa: F401
  ```

---

### Task 3: 生成迁移并检查

**Files:**
- Create: `D:\two\backend\alembic\versions\xxxx_m2_core_tables.py`

- [ ] **Step 3.1: 生成 autogenerate 迁移**

  ```bash
  cd D:\two\backend
  alembic revision --autogenerate -m "create core tables"
  ```

- [ ] **Step 3.2: 人工检查迁移文件**

  检查重点：
  1. 每个 Enum 的 `create_type=True` 是否出现在 `op.create_table()` 中
  2. 外键列和 REFERENCES 是否正确（对照设计文档的外键约束表）
  3. 建表顺序是否符合依赖图（merchants → shops → platform_shops → reviews/menu_items → crawl_jobs/reports/manual_imports）
  4. `downgrade()` 中 `op.drop_table()` 顺序与 `upgrade` 相反

- [ ] **Step 3.3: 执行迁移**

  ```bash
  cd D:\two\backend
  alembic upgrade head
  ```

  预期输出类似：`INFO  [alembic.runtime.migration] Running upgrade 09ee12f576bb -> xxxx (create core tables)`

---

### Task 4: 写 Schema + Router

**Files:**
- Create: `D:\two\backend\app\schemas\merchant.py`
- Create: `D:\two\backend\app\schemas\shop.py`
- Create: `D:\two\backend\app\api\v1\merchants.py`
- Create: `D:\two\backend\app\api\v1\shops.py`
- Modify: `D:\two\backend\app\api\v1\__init__.py`
- Modify: `D:\two\backend\app\main.py`

#### Schema 公共分页模型

- [ ] **Step 4.1: 创建 schemas/common.py**

  ```python
  """通用 Pydantic schema。"""
  from __future__ import annotations

  from pydantic import BaseModel


  class PaginatedResponse(BaseModel):
      items: list
      total: int
      page: int
      size: int
  ```

#### Merchant Schema + Router

- [ ] **Step 4.2: 创建 schemas/merchant.py**

  ```python
  """商家 Pydantic schema。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime

  from pydantic import BaseModel, ConfigDict


  class MerchantCreate(BaseModel):
      name: str = ""
      contact_name: str | None = None
      contact_phone: str | None = None
      tier: str = "trial"
      notes: str | None = None


  class MerchantUpdate(BaseModel):
      name: str | None = None
      contact_name: str | None = None
      contact_phone: str | None = None
      tier: str | None = None
      notes: str | None = None


  class MerchantResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)

      id: uuid.UUID
      user_id: uuid.UUID
      name: str
      contact_name: str | None = None
      contact_phone: str | None = None
      tier: str
      notes: str | None = None
      created_at: datetime
  ```

- [ ] **Step 4.3: 创建 api/v1/merchants.py**

  包含 5 个 handler：
  - `GET /api/v1/merchants` — 列表（name 模糊搜索 + 分页）
  - `POST /api/v1/merchants` — 创建
  - `GET /api/v1/merchants/{mid}` — 详情
  - `PATCH /api/v1/merchants/{mid}` — 更新
  - `DELETE /api/v1/merchants/{mid}` — 删除

  所有路由需要 `Depends(get_current_user)` 保护。创建时 `user_id` 从当前用户取。

  ```python
  """商家 CRUD API。"""
  from __future__ import annotations

  from fastapi import APIRouter, Depends, HTTPException, status
  from sqlalchemy import select, func
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.core.database import get_db
  from app.core.deps import get_current_user
  from app.models.merchant import Merchant
  from app.models.user import User
  from app.schemas.merchant import MerchantCreate, MerchantResponse, MerchantUpdate

  router = APIRouter(prefix="/merchants", tags=["merchants"])


  @router.get("", response_model=dict)
  async def list_merchants(
      page: int = 1,
      size: int = 20,
      name: str | None = None,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      query = select(Merchant).where(Merchant.user_id == current_user.id)
      count_query = select(func.count(Merchant.id)).where(Merchant.user_id == current_user.id)
      if name:
          query = query.where(Merchant.name.ilike(f"%{name}%"))
          count_query = count_query.where(Merchant.name.ilike(f"%{name}%"))
      total = (await db.execute(count_query)).scalar() or 0
      result = await db.execute(query.offset((page - 1) * size).limit(size))
      items = [MerchantResponse.model_validate(m) for m in result.scalars().all()]
      return {"items": items, "total": total, "page": page, "size": size}


  @router.post("", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
  async def create_merchant(
      body: MerchantCreate,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      merchant = Merchant(
          user_id=current_user.id,
          **body.model_dump(exclude_unset=True),
      )
      db.add(merchant)
      await db.flush()
      return MerchantResponse.model_validate(merchant)


  @router.get("/{mid}", response_model=MerchantResponse)
  async def get_merchant(
      mid: str,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      result = await db.execute(
          select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
      )
      merchant = result.scalar_one_or_none()
      if not merchant:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
      return MerchantResponse.model_validate(merchant)


  @router.patch("/{mid}", response_model=MerchantResponse)
  async def update_merchant(
      mid: str,
      body: MerchantUpdate,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      result = await db.execute(
          select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
      )
      merchant = result.scalar_one_or_none()
      if not merchant:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
      for k, v in body.model_dump(exclude_unset=True).items():
          setattr(merchant, k, v)
      await db.flush()
      return MerchantResponse.model_validate(merchant)


  @router.delete("/{mid}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_merchant(
      mid: str,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      result = await db.execute(
          select(Merchant).where(Merchant.id == mid, Merchant.user_id == current_user.id)
      )
      merchant = result.scalar_one_or_none()
      if not merchant:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
      await db.delete(merchant)
  ```

#### Shop Schema + Router

- [ ] **Step 4.4: 创建 schemas/shop.py**

  ```python
  """门店 Pydantic schema。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime

  from pydantic import BaseModel, ConfigDict

  from app.schemas.platform_shop import PlatformShopResponse


  class ShopCreate(BaseModel):
      name: str = ""
      address: str | None = None
      phone: str | None = None
      category: str | None = None


  class ShopUpdate(BaseModel):
      name: str | None = None
      address: str | None = None
      phone: str | None = None
      category: str | None = None
      status: str | None = None


  class ShopResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)

      id: uuid.UUID
      merchant_id: uuid.UUID
      name: str
      address: str | None = None
      phone: str | None = None
      category: str | None = None
      status: str
      created_at: datetime
  ```

- [ ] **Step 4.5: 创建 schemas/platform_shop.py**

  ```python
  """平台店铺 Pydantic schema。"""
  from __future__ import annotations

  import uuid
  from datetime import datetime

  from pydantic import BaseModel, ConfigDict


  class PlatformShopCreate(BaseModel):
      platform: str
      platform_shop_id: str | None = None
      shop_url: str | None = None
      shop_name: str | None = None


  class PlatformShopResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)

      id: uuid.UUID
      shop_id: uuid.UUID
      platform: str
      platform_shop_id: str | None = None
      shop_url: str | None = None
      shop_name: str | None = None
      rating: float | None = None
      monthly_sales: int | None = None
      total_reviews: int | None = None
      last_synced_at: datetime | None = None
      created_at: datetime
  ```

- [ ] **Step 4.6: 创建 api/v1/shops.py**

  嵌套路由（列表/创建在 merchant 下）:
  - `GET /api/v1/merchants/{mid}/shops` — 按商家列出门店
  - `POST /api/v1/merchants/{mid}/shops` — 创建门店

  扁平路由:
  - `GET /api/v1/shops/{sid}` — 门店详情
  - `PATCH /api/v1/shops/{sid}` — 更新
  - `DELETE /api/v1/shops/{sid}` — 删除
  - `GET /api/v1/shops/{sid}/platforms` — 平台店铺列表
  - `POST /api/v1/shops/{sid}/platforms` — 绑定平台店铺

- [ ] **Step 4.7: 注册所有 Router**

  更新 `api/v1/__init__.py`：

  ```python
  from app.api.v1.auth import router as auth_router
  from app.api.v1.merchants import router as merchants_router
  from app.api.v1.shops import router as shops_router

  routers = [auth_router, merchants_router, shops_router]
  ```

---

### Task 5: 写 seed.py

**Files:**
- Create: `D:\two\backend\scripts\seed.py`

- [ ] **Step 5.1: 创建 scripts/seed.py**

  使用 `asyncio.run()` 启动 async seed 函数。流程：
  1. 创建 engine 连接 PG
  2. 创建用户 admin@test.com / admin123
  3. 创建 2 个商家（"川味坊火锅" user_id=admin.id，"星巴克咖啡" user_id=admin.id）
  4. 川味坊火锅 3 个门店（解放碑店、观音桥店、南坪店）
  5. 星巴克咖啡 2 个门店（时代天街店、万象城店）
  6. 部分门店绑定平台店铺（美团/抖音）
  7. 为川味坊解放碑店添加 3 条示例评价

  关键代码结构：

  ```python
  """开发种子数据。"""
  import asyncio
  from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
  from app.core.security import hash_password
  from app.models import User, Merchant, Shop, PlatformShop, Review

  async def seed():
      engine = create_async_engine("postgresql+asyncpg://aistro:aistro@localhost:5432/aistro")
      session_factory = async_sessionmaker(engine, expire_on_commit=False)
      async with session_factory() as db:
          # ... 插入数据
          await db.commit()
      await engine.dispose()

  if __name__ == "__main__":
      asyncio.run(seed())
  ```

---

### Task 6: 验证

- [ ] **Step 6.1: 运行 seed**

  ```bash
  cd D:\two\backend
  python -m scripts.seed
  ```

- [ ] **Step 6.2: 启动后端并测试 API**

  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```

  用 curl 验证：
  ```bash
  # 登录获取 token
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@test.com","password":"admin123"}'

  # 列出门店（用返回的 token）
  curl http://localhost:8000/api/v1/merchants/{mid}/shops \
    -H "Authorization: Bearer <token>"
  ```

---

### Task 7: 前端商家/门店页面

**Files:**
- Create: `D:\two\frontend\src\pages\MerchantsPage.tsx`
- Create: `D:\two\frontend\src\pages\MerchantDetailPage.tsx`
- Create: `D:\two\frontend\src\services\merchants.ts`
- Modify: `D:\two\frontend\src\App.tsx`

- [ ] **Step 7.1: 创建 services/merchants.ts**

  ```typescript
  import api from "./api";

  export interface Merchant {
    id: string;
    user_id: string;
    name: string;
    contact_name: string | null;
    contact_phone: string | null;
    tier: string;
    notes: string | null;
    created_at: string;
  }

  export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    page: number;
    size: number;
  }

  export const merchantService = {
    list: (params?: { page?: number; size?: number; name?: string }) =>
      api.get<PaginatedResponse<Merchant>>("/merchants", { params }),
    create: (data: Partial<Merchant>) =>
      api.post<Merchant>("/merchants", data),
    get: (id: string) =>
      api.get<Merchant>(`/merchants/${id}`),
    update: (id: string, data: Partial<Merchant>) =>
      api.patch<Merchant>(`/merchants/${id}`, data),
    delete: (id: string) =>
      api.delete(`/merchants/${id}`),
  };
  ```

- [ ] **Step 7.2: 创建 services/shops.ts**

  ```typescript
  import api from "./api";

  export interface Shop {
    id: string;
    merchant_id: string;
    name: string;
    address: string | null;
    phone: string | null;
    category: string | null;
    status: string;
    created_at: string;
  }

  export const shopService = {
    listByMerchant: (mid: string) =>
      api.get<Shop[]>(`/merchants/${mid}/shops`),
    create: (mid: string, data: Partial<Shop>) =>
      api.post<Shop>(`/merchants/${mid}/shops`, data),
    get: (sid: string) =>
      api.get<Shop>(`/shops/${sid}`),
    update: (sid: string, data: Partial<Shop>) =>
      api.patch<Shop>(`/shops/${sid}`, data),
    delete: (sid: string) =>
      api.delete(`/shops/${sid}`),
  };
  ```

- [ ] **Step 7.3: 创建 MerchantsPage.tsx**

  Ant Design Table 列表页，功能：
  - 搜索框（name 过滤）
  - 表格列：名称、联系人、电话、套餐等级、创建时间
  - 新建按钮 → Modal 表单
  - 行点击 → 跳转到商家详情页
  - 行操作：编辑、删除

- [ ] **Step 7.4: 创建 MerchantDetailPage.tsx**

  商家详情页，功能：
  - 商家信息卡片
  - 门店 Table（嵌套在商家下）
  - 新建门店 → Modal 表单
  - 门店行操作：编辑、删除

- [ ] **Step 7.5: 更新 App.tsx 路由**

  追加：
  ```typescript
  <Route path="/merchants" element={<ProtectedRoute><MerchantsPage /></ProtectedRoute>} />
  <Route path="/merchants/:id" element={<ProtectedRoute><MerchantDetailPage /></ProtectedRoute>} />
  ```

  Dashboard 页面的"商家管理"入口也添加 Link 导航。

---

### Task 8: 提交

- [ ] **Step 8.1: Commit**

  ```bash
  cd D:\two
  git add -A
  git commit -m "feat: M2 core data models and CRUD"
  ```

