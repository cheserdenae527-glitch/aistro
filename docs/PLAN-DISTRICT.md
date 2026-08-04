# 商圈分析板块 — 实现计划

> 基于 SPEC-DISTRICT v0.5 · 独立于主项目里程碑

## 依赖与前置

| 项 | 说明 |
|---|---|
| 高德 Web API Key | AMAP_WEB_API_KEY / AMAP_JS_KEY / AMAP_SECURITY_JS_CODE 写入 `.env` |
| 门店地址 | `shops.address` 必须可地理编码 |
| shops.category 枚举 | K1 先核对实际枚举值，映射表按实际值对齐 |
| 高德 MCP | 已接入，仅调研辅助，不阻塞 |

---

## K1 — 后端：高德集成 + 快照 API

**目标**：地理编码（白名单精度校验）、POI 聚合（含清洗）、两段式落库、统计、配额保护 API 可用。

### 任务清单

1. 配置：AMAP_WEB_API_KEY / AMAP_JS_KEY / AMAP_SECURITY_JS_CODE 进 config + .env.example
2. Alembic 迁移：district_snapshots / district_pois
   - snapshot 含 geocode_level / density_per_km2 / mapping_status
   - POI 含 excluded_as_self
3. SQLAlchemy 模型 + Pydantic Schema
4. 高德 Service：
   - geocode(address) → (lng, lat, level)，白名单外抛 400；**502/超时重试 1 次**（退避 200ms），仍失败不建记录
   - place_around 分页 + 早停（空页/不足 25 条终止）
   - **单页瞬时错误重试**：502/超时重试 1 次，退避 200ms → 500ms；配额超限不重试
   - 重试请求同样计入日配额计数
   - 配额超限/网络错误映射（429/502）
   - 账号级日配额计数 + 熔断（**Asia/Shanghai 时区 key**）
5. 清洗逻辑：
   - 排除门店自身：名称归一化相似（长度 ≥3 才参与）+ distance_m < 10；短名称不排除
   - 被排除 POI **仍落库**，`excluded_as_self=true`（可反查）
   - 竞品映射两态（full / none）+ shops.category 空值 → none
6. **两段式流程**：
   - Step A 无事务：输入校验（400 不建记录，不种下频控）→ **种下 60s 频控 token** → 地理编码（含重试，失败不建记录）→ 周边搜索（中途失败建 failed snapshot）→ 清洗
   - Step B 单 DB 事务：仅 A 成功才写 snapshot(analyzed) + 全部 POI（含 excluded_as_self 记录）
   - **`poi_total` / `category_stats` / `density_per_km2` 口径**：均只统计 `excluded_as_self=false` 的 POI（不含门店自身）；`excluded_self_count` 作为独立字段单独展示，不并入 `poi_total`
7. API：
   - 门店资源统一嵌套 `/shops/{shop_id}/district/`：analyze / latest / snapshots（分页倒序 + status 过滤）/ 详情（POI 分页，excluded 默认折叠）/ competitors
   - 全局 `/api/v1/district/map-config`（JWT 登录即可）
   - securityJsCode 代理 `/district/_AMapService/*`
8. 密度动态计算：`poi_total / (π × (radius_m/1000)²)`
9. 频控：Redis `SET NX EX`（现有实现确认），60s + 日配额熔断
10. 测试（mock 高德）：
    - 地理编码成功 / 失败（400 不建记录）/ 白名单外 level → 400 不建记录
    - 地理编码重试：第一次 502、第二次成功 → 整体成功；两次失败 → 不建记录
    - 分页早停（不足 25 条只拉 1 页）
    - 重试：单页第一次 502、第二次成功 → 整体成功（重试计入日配额）；两次失败 → failed snapshot
    - 自身排除：名称相似 + <10m 排除并落 excluded_as_self=true；同品牌分店不误排除；短名称不排除
    - **`poi_total` 口径**：含 1 条 excluded_as_self 的场景下，`poi_total`/`density_per_km2`/`category_stats` 均不计入该条，`excluded_self_count` 单独等于 1
    - 竞品映射：full / category 空 none
    - 密度随 radius_m 变化
    - 快照列表分页 + 倒序 + status 过滤
    - 两段式：周边搜索失败建 failed 快照无 POI；输入校验失败不建记录
    - **频控种下时机**：纯输入校验 400 不消耗冷却，可立即重试；通过校验后地理编码失败已消耗冷却
    - 日配额熔断（Asia/Shanghai 日期）
    - 路径归属：门店资源跨用户 404；map-config 登录即可访问
11. 契约文档：`docs/contracts/district-api.md`
    - 显式写清归属校验链（shop → merchant → user）
    - 写清 map-config 全局端点约定 + serviceHost 代理
    - 写清失败留痕规则（哪些失败建 failed 快照，哪些不建）

### 交付物
- Swagger 可调用全部 API
- pytest 全绿 + 契约文档
- 真实高德 Key 由用户提供后联调

---

## K2 — 前端商圈页面

**目标**：地图可视化 + 概览 + 竞品列表。

```
前置：K1
```

### 任务清单

1. 路由 `/district` + `/district/:shop_id`，侧边栏入口
2. 门店选择页
3. 高德 JS API 地图：
   - 全局 map-config 取 key（无需 shop_id）
   - `window._AMapSecurityConfig = { serviceHost: "/api/v1/district/_AMapService" }`
   - **不把 securityJsCode 打进前端 bundle**
4. 概览卡（POI 总数 / 品类数 / 竞品数 / 商圈密度）
5. 品类分布柱状图
6. 竞品列表（mapping_status=none 提示）
7. 重新分析（429 倒计时 + analyzing loading）
8. 历史快照切换：默认 `status=analyzed`，分页加载；失败快照可展开看 error_message
9. 真实 API 联调：Swagger 反查契约文档，不一致回写
10. 单元测试（Vitest）：统计展示逻辑、loading 状态、分页、status 过滤

### 交付物
- 地图 + 概览 + 竞品列表完整可用
- 安全密钥代理走通，前端无密钥

---

## K3 — 真实数据验证

**目标**：用真实高德 Key 验证端到端。

```
前置：K1 + K2
```

### 任务清单

1. 真实门店地址跑地理编码（验证 level 白名单）
2. 周边搜索 + 分页早停 + 重试 + 自身排除（核对 excluded_as_self）
3. 竞品映射人工核对（mapping_status）
4. 地图标记渲染检查（桌面/移动）
5. 日配额计数验证（阈值可临时调小，确认 Asia/Shanghai 日期）
6. 快照列表分页 + status 过滤验证
7. 契约一致性反查 + 文档回写

### 交付物
- 真实商圈快照可生成、可展示
- 地图正常渲染、安全密钥代理正常

---

## 执行顺序

```
K1 (后端) → K2 (前端) → K3 (真实数据验证)
```

每阶段独立对话，K2/K3 引用 `docs/contracts/district-api.md`。

## 已知妥协

- 高德周边搜索单次最多 100 条 POI，超大体量会截断
- 商圈密度用 POI 数量/面积近似，不接高德付费人流数据
- 评分/价格等深度数据后续对接美团/点评
- analyze 同步长耗时（约 2-10s），MVP 用前端 loading；后续可切异步任务
- 快照不自动清理，后续加每店保留最近 50 份 + 定时清理
- 日配额熔断阈值先按 8000/日默认，接入真实 Key 后按套餐调整
- 自身排除基于名称+距离启发式，边缘情况（同品牌分店 <10m）靠 excluded_as_self 明细可追溯，后续可加人工确认机制
