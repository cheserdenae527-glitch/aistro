# D1 Findings

## 基础设施
- 测试数据库：`aistro_test`（conftest 自动 drop_all/create_all，不需要跑迁移）。
- 频控依赖 Redis；MinIO 用于图片落盘；现有测试都走真实服务。
- `rg` 在当前 Codex 环境启动失败（WindowsApps 拒绝访问），改用 `Get-ChildItem`/`Select-String`。

## 现有模式
- 鉴权 helper：`_verify_shop_owner(shop_id, user, db)` 在 profiles.py，join Shop->Merchant->User，失败 404。
- 存储：`app.services.storage` 的 `upload_bytes` / `get_presigned_url` / `get_object_bytes` / `safe_get_presigned_url`。
- 豆包：`app.ai.doubao_image._generate_image(prompt, size, ref_data, ref_mime)`，一次 4 张。
- 频控：`check_rate_limit(key, ttl)`，Redis 不可用放行。
- 敏感词：`contains_blocked(text)`。
- 模型：UUID PK + DateTime(timezone=True)，status 用 sa.Enum。

## 测试基建注意
- 原 conftest client 是 module 级：跨模块换事件循环会让全局 Redis/SQLAlchemy 连接池失效
  （表现为 Redis 频控跳过、asyncpg InvalidCachedStatementError）。已改为 session 级。
- 测试不要为查 DB 另起 `asyncio.run` 引擎，避免与 TestClient 事件循环交错；
  改为 API `include_derived=true` 反查状态。
