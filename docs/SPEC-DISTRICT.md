# AiRestro — 商圈分析板块 设计规约

> 版本：v0.5 · 2026-08-04
> 状态：定稿 · 自成一类模块
> 变更：v0.4 → v0.5 修正 poi_total 口径回归（排除自身后计数）、geocode 重试补齐、频控种下时机明确

---

## 1. 模块定位

独立入口（侧边栏"商圈分析"）。基于高德开放平台 Web API，把门店周边餐饮商圈聚合、可视化、保存快照，为选址/竞对调研/内容选题提供数据底座。

MVP 覆盖高德能提供的数据：POI 聚合、品类分布、竞品列表、地图可视化。评分/价格/活动等深度数据后续对接美团/点评。

> 高德 MCP 已接入 Codex 环境，作为深度调研辅助工具；产品功能统一走高德 Web API，不依赖 MCP。

---

## 2. 高德 API 集成

| 能力 | 接口 | 用途 |
|---|---|---|
| 地理编码 | `/v3/geocode/geo` | 门店地址 → 经纬度 |
| 周边搜索 | `/v3/place/around` | 门店 3km 内餐饮 POI 聚合 |
| JS API | 前端地图 | 门店 + POI 地图标记 |

配置（`.env`，高德开放平台申请）：
- `AMAP_WEB_API_KEY`：后端 REST API
- `AMAP_JS_KEY`：前端 JS API
- `AMAP_SECURITY_JS_CODE`：高德安全密钥，**只存后端**

### 2.1 地理编码精度校验（白名单策略）

高德 geocode 返回 `level` 字段。**采用白名单放行，其余一律拒绝**，不枚举不可用值：

- 白名单：门牌号 / 道路 / 兴趣点 / 地名
- 不在白名单（含未来新增的未知 level）→ 400，提示"门店地址过于模糊，请补充门牌号或详细地址"
- **瞬时错误重试**：geocode 调用 502/超时重试 1 次，退避 200ms（与 2.2 周边搜索一致）；仍失败才报错、不建记录

### 2.2 周边搜索

- `location=lng,lat radius=3000 types=050000`
- 分页：每页 25，最多 4 页（100 条）
- **分页早停**：某页返回为空或不足 25 条时提前终止，节省高德配额
- **瞬时错误重试**：单页 502/超时重试 1 次，指数退避 200ms → 500ms；仍失败才真正报错
- 重试请求同样计入日配额计数（真实发起了对高德的调用）
- 配额超限（`DAILY_QUERY_OVER_LIMIT`）→ 429"今日配额已用尽"（不重试）

### 2.3 高德 JS API 安全密钥（代理模式）

前端**不直接打包 securityJsCode**：
- 后端代理：`GET /api/v1/district/_AMapService/*` 转发高德 `securityConfig` 请求
- 前端地图初始化设置 `window._AMapSecurityConfig = { serviceHost: "/api/v1/district/_AMapService" }`
- `AMAP_SECURITY_JS_CODE` 只存在于后端环境变量

---

## 3. 竞品判定

### 3.1 映射表

| shops.category | 竞品高德类型 |
|---|---|
| 火锅 | 火锅店 |
| 烧烤 | 烧烤 |
| 快餐 | 快餐厅 / 小吃快餐店 |
| 咖啡 | 咖啡厅 |
| 甜品/烘焙 | 甜品饮品 |
| 日料 | 日本料理 |
| 西餐 | 西餐厅 |

**K1 必须核对 `shops.category` 实际枚举值**，按实际存储值对齐映射表。

### 3.2 mapping_status（两态，MVP 无 partial）

| 状态 | 触发条件 |
|---|---|
| full | 门店 category 非空且精确命中映射表 |
| none | category 为空 / 未命中映射表 |

**MVP 砍掉 partial**：映射表已无宽泛兜底，不存在"部分命中"业务场景。后续若引入大类命中多个子品类再补回。

### 3.3 自身排除（防连锁误伤，保留明细）

排除门店自身 POI 的条件：
1. 名称归一化后相似（规则见下）
2. `distance_m < 10`

被排除的 POI **同样写入 `district_pois`**，`excluded_as_self=true`，保留可追溯明细：
- `excluded_self_count` 由 `COUNT(excluded_as_self=true)` 派生
- 出问题时可以反查具体是哪条 POI 被排除，而不是只有一个数字

名称相似规则（避免短名称误伤）：
- 归一化：去空格/标点，统一大小写
- 归一化后长度 <3：**不参与排除**（"茶"/"面"这种短名互相包含无意义）
- 长度 ≥3：互相包含 或 difflib 相似度 ≥0.85 视为相似

连锁品牌分店（如"海底捞·XX店"）距离通常 >10m 且 poi_id 不同，不会被误排除。

---

## 4. 数据模型

### district_snapshots（商圈快照）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK → shops | |
| center_lng / center_lat | numeric | 门店坐标（地理编码结果） |
| geocode_level | varchar(50) | 地理编码精度等级 |
| radius_m | int | 默认 3000 |
| poi_total | int | POI 总数（**已排除门店自身**，即 `excluded_as_self=false` 的计数） |
| competitor_count | int | 竞品数 |
| category_stats | jsonb | 品类分布 [{ category, count }]（不含 excluded_as_self 的 POI） |
| density_per_km2 | numeric | 商圈密度 = poi_total / (π × (radius_m/1000)²)，**不含自身** |
| mapping_status | enum full / none | 品类映射状态 |
| status | enum analyzed / failed | |
| error_message | text | 仅 failed 快照记录失败原因 |
| created_at | timestamptz | |

`excluded_self_count` 由 `district_pois` 中 `excluded_as_self=true` 计数派生，不单独存储，**作为独立展示字段**（"另有 N 条被识别为门店自身，已排除"），不并入 `poi_total`。

> **v0.5 修正**：v0.4 曾将 `poi_total` 误改为"排除前"口径，与"自身排除"功能的设计意图矛盾（门店自己不该被算进周边商圈统计），现改回"排除后"口径。`poi_total`、`category_stats`、`density_per_km2` 三处统计均只基于 `excluded_as_self=false` 的 POI。

### district_pois（POI 记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| snapshot_id | UUID FK → district_snapshots | |
| poi_id | varchar(50) | 高德 POI ID |
| name | varchar(200) | |
| category | varchar(100) | 高德类型名 |
| address | text | |
| lng / lat | numeric | |
| distance_m | int | 距门店距离 |
| is_competitor | boolean | 竞品标记（被排除自身为 false） |
| excluded_as_self | boolean | 是否被判定为门店自身（默认 false） |
| created_at | timestamptz | |

唯一索引：`(snapshot_id, poi_id)`。

---

## 5. 分析流程（两段式 + 失败留痕规则）

高德外部调用不在 DB 事务范围内，真实执行顺序是两段式：

```
Step A（无 DB 事务）：高德调用
  1. 输入校验（地址非空/格式）→ 400，不建记录，不种下频控 token
  2. 种下 60s 频控 token（Redis SET NX EX）
  3. 地理编码（含 502/超时重试 1 次）→ 精度白名单校验
     · 输入类失败（地址无法解析/精度不足）→ 400，不建记录
     · 高德调用失败（重试后仍失败）→ 不建记录（尚未开始正经分析）
  4. 周边搜索全部分页（含单页重试，计入日配额）
     · 任一页最终失败（重试后仍失败）→ 建 status=failed 快照
       （已发起高德搜索，属于分析中途失败，需留痕）
     · 配额熔断 → 429，不建记录（未发起本次搜索）
  5. 清洗：自身排除（写 excluded_as_self）+ 竞品映射

Step B（DB 事务，仅 A 成功才执行）：
  6. 单事务内创建 snapshot(status=analyzed) + 批量写入全部 POI（含 excluded_as_self 的记录）
  7. 统计 poi_total / competitor_count / category_stats / density_per_km2
     （均基于 excluded_as_self=false 的 POI）
```

**失败留痕规则**：
- 纯输入校验错误（400）：不建记录
- 地理编码调用失败（尚未开始搜索）：不建记录
- 周边搜索中途失败（已发起搜索）：建 `status=failed` + `error_message`，无 POI
- 配额熔断（429）：不建记录

重复分析：每次生成新快照（保留历史），不覆盖。

---

## 6. API

全部 JWT 鉴权 + shop 所有权校验（shop → merchant → user）。

```
POST /api/v1/shops/{shop_id}/district/analyze
  → 频控 60s（user+shop）
  → 返回 { snapshot_id, poi_total, competitor_count, density_per_km2,
           mapping_status, excluded_self_count }

GET  /api/v1/shops/{shop_id}/district/latest
GET  /api/v1/shops/{shop_id}/district/snapshots?page=1&size=20&status=
  → 按 created_at 倒序，默认 size=20，上限 100
  → status 过滤可选（analyzed/failed）；前端历史切换默认只传 analyzed
GET  /api/v1/shops/{shop_id}/district/snapshots/{snapshot_id}
  → 详情 + POI 列表（分页；excluded_as_self=true 的 POI 默认折叠，可展开）
GET  /api/v1/shops/{shop_id}/district/snapshots/{snapshot_id}/competitors

GET  /api/v1/district/map-config
  → 全局端点（不依赖 shop_id）：返回 { amap_js_key, proxy_path }
  → 仍需要 JWT 登录，但不做 shop 归属校验（Key 是账号级共享资源）
```

**频控原子性**：60s 频控使用 Redis `SET NX EX` 原子操作（现有 `check_rate_limit` 已如此实现），禁止"先 GET 判断再 SET"的非原子写法。

**频控种下时机**：仅在**通过输入校验、即将发起地理编码调用**时才种下 60s 频控 token。纯输入校验错误（地址为空/格式错误等，400）不消耗冷却时间，允许用户立即修正后重试；地理编码或周边搜索失败（无论是否已建 failed 快照）已消耗一次冷却，不额外豁免。

**路径统一**：门店相关资源嵌套 `/shops/{shop_id}/district/`；`map-config` 与门店无关放全局。

---

## 7. 配额保护

| 层 | 机制 |
|---|---|
| 单用户单店 | 60s 频控（Redis SET NX EX，user+shop） |
| 账号级日配额 | Redis 计数 `amap_daily_quota:{yyyy-mm-dd}`，日期用 **Asia/Shanghai 时区**生成（高德配额按北京时间自然日重置）；每次高德调用 +1；超过阈值（默认 8000，可配置）熔断，返回 429"今日高德配额已用尽" |
| 高德超限 | 映射为 429 + 高德错误原文 |

---

## 8. 前端

```
DistrictIndexPage（/district）→ 门店选择
DistrictDetailPage（/district/:shop_id）
├─ 高德地图（JS API：门店 + 竞品 POI 标记；securityJsCode 走后端代理）
├─ 概览卡：POI 总数 / 品类数 / 竞品数 / 商圈密度（家/km²）
├─ 品类分布柱状图
├─ 竞品列表（名称/品类/距离/地址；mapping_status=none 时提示）
└─ 操作：重新分析（429 倒计时 + analyzing loading）/ 历史快照切换（默认只看 analyzed，分页）
```

`analyze` 为同步长耗时（1 次地理编码 + 最多 4 次周边搜索 + 落库），前端必须提供 analyzing loading 态，后端超时建议 60s。

---

## 9. MVP 边界

### 包含
- 地理编码（白名单精度校验 + 瞬时错误重试）+ 周边餐饮 POI 聚合（3km，≤100 条，分页早停 + 单页重试）
- 门店自身排除（明细保留 excluded_as_self，可反查）
- 竞品映射（mapping_status: full / none）
- 两段式流程：外部调用与 DB 事务分离，失败留痕规则明确
- 商圈快照事务落库 + 历史列表（分页 + status 过滤）+ 密度动态计算
- 高德 JS API 地图（安全密钥后端代理）
- 账号级日配额熔断（Asia/Shanghai 时区）
- 重新分析（新快照，不覆盖）

### 不包含
- 评分/价格/活动等深度数据（后续对接美团/点评/口碑）
- 商圈热度（高德付费人流数据）
- 竞品菜单对比（后续）
- 商圈变化对比报告（后续基于快照历史）
- 高德 MCP 深度调研的产品化（MCP 留给 agent 流程）
- 快照自动清理（**已知妥协**：MVP 不清理，后续加每店保留最近 50 份 + 定时清理）

---

## 10. 复用清单

| 能力 | 来源 |
|---|---|
| JWT + shop 所有权 | `app.core.deps` + 装修模块 helper |
| 门店数据 | `shops` 表 |
| 频控 | `app.core.rate_limit`（SET NX EX） |
| Redis 计数 | `app.core.rate_limit` 同栈 |
| 前端图表 | Ant Design Charts / Recharts |
| 高德 MCP | 已接入，调研辅助（非产品依赖） |
