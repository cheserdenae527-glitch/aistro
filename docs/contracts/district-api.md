# 商圈分析 API 接口契约

> 版本：v1.0 · 2026-08-04
> 基于：SPEC-DISTRICT v0.5 · K1 交付

## 通用约定

- **Base URL**: `/api/v1`
- **鉴权**: 除 `_AMapService` 代理外，所有端点需 `Authorization: Bearer <JWT>`
- **归属校验链**: 所有 `/shops/{shop_id}/...` 资源校验 `shop -> merchant -> user`，非所有者返回 404
- **失败留痕**: 输入校验/地理编码失败不建记录；周边搜索中途失败建 `status=failed` 快照

---

## 1. 分析

### POST /shops/{shop_id}/district/analyze

触发高德地理编码 + 周边搜索（3km 餐饮 POI）并生成新快照（不覆盖历史）。

**频控**: 60s，key = `rate_limit:district_analyze:{user_id}:{shop_id}`；输入校验 400 不消耗冷却。

**成功响应** `200`:
```json
{
  "snapshot_id": "uuid",
  "poi_total": 42,
  "competitor_count": 8,
  "density_per_km2": 1.49,
  "mapping_status": "full",
  "excluded_self_count": 1
}
```

**错误码**:
| 状态码 | 场景 |
|---|---|
| 400 | 门店地址为空 / 无法解析 / 精度不足（白名单外） |
| 404 | shop 不存在或非所有者 |
| 429 | 60s 频控 / 今日高德配额已用尽 |
| 502 | 周边搜索重试后失败（已建 failed 快照） |

口径：`poi_total / category_stats / density_per_km2` 均基于 `excluded_as_self=false` 的 POI。

---

## 2. 快照查询

### GET /shops/{shop_id}/district/latest

最新快照（任意 status）。无快照返回 404。

### GET /shops/{shop_id}/district/snapshots?page=&size=&status=

- `page` 默认 1；`size` 默认 20，上限 100
- `status` 可选 `analyzed` / `failed`
- 按 `created_at` 倒序

**响应**:
```json
{
  "items": [
    {
      "id": "uuid", "shop_id": "uuid",
      "center_lng": 104.081, "center_lat": 30.655,
      "geocode_level": "门牌号", "radius_m": 3000,
      "poi_total": 42, "competitor_count": 8,
      "category_stats": [{"category": "火锅店", "count": 8}],
      "density_per_km2": 1.49,
      "mapping_status": "full", "status": "analyzed",
      "error_message": null, "excluded_self_count": 1,
      "created_at": "2026-08-04T..."
    }
  ],
  "total": 3, "page": 1, "size": 20
}
```

### GET /shops/{shop_id}/district/snapshots/{snapshot_id}?page=&size=&include_excluded=

详情 + POI 列表。`include_excluded=false`（默认）折叠被排除的自身 POI。

### GET /shops/{shop_id}/district/snapshots/{snapshot_id}/pois?page=&size=&include_excluded=

独立 POI 列表接口。

### GET /shops/{shop_id}/district/snapshots/{snapshot_id}/competitors

`is_competitor=true` 的 POI，按距离升序：
```json
[
  {
    "poi_id": "B000A7XXXX",
    "name": "隔壁火锅",
    "category": "火锅店",
    "address": "春熙路100号",
    "distance_m": 300,
    "lng": 104.091,
    "lat": 30.655
  }
]
```

---

## 3. 地图配置

### GET /district/map-config

全局端点（JWT 登录即可，无 shop 归属校验）。返回前端地图初始化所需 key：
```json
{ "amap_js_key": "xxxx", "proxy_path": "/api/v1/district/_AMapService" }
```
未配置 JS Key 返回 503。

### GET /district/_AMapService/{path}

高德 JS API 安全密钥代理（**无需 JWT**，地图初始化请求不带 token）。后端转发到 `https://restapi.amap.com/securityConfig` 并附加 `key` + `jscode`。

前端约定：
```js
window._AMapSecurityConfig = { serviceHost: "/api/v1/district/_AMapService" };
```

---

## 4. 高德配置（.env）

| 变量 | 说明 |
|---|---|
| AMAP_WEB_API_KEY | 后端 REST API Key |
| AMAP_JS_KEY | 前端 JS API Key |
| AMAP_SECURITY_JS_CODE | 高德安全密钥（只存后端，经代理转发） |
| AMAP_DAILY_QUOTA_LIMIT | 账号级日配额熔断阈值（默认 8000，Asia/Shanghai 自然日） |
