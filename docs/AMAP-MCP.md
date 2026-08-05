# 高德地图 MCP 接入文档

> 版本：v0.1 · 对应后端 maps 模块（`app/services/amap_mcp.py` + `app/api/v1/maps.py`）
> 服务来源：[ModelScope MCP 广场 @amap/amap-maps](https://modelscope.cn/mcp/servers/@amap/amap-maps) / 高德官方 MCP

通过 MCP 协议接入高德地图能力：地理编码、逆地理编码、IP 定位、天气、
距离测量、POI 搜索（竞品/商圈）、路径规划（驾车/步行/骑行/公交）。
接入后 AiRestro 后端即可为 AI Agent 与前端提供统一的地图查询接口。

---

## 1. 前置准备：申请高德 Key

1. 注册并登录 [高德开放平台](https://lbs.amap.com/)。
2. 进入「控制台 → 应用管理 → 我的应用 → 创建新应用」。
3. 在应用下「添加 Key」，服务平台选择 **Web 服务**。
4. 记下生成的 Key（形如 `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）。

> 个人开发者有免费调用额度，可在控制台「配额管理」查看每日上限。

---

## 2. 两种接入方式

### 方式 A：ModelScope 托管（MCP 广场）

1. 打开 [ModelScope MCP 广场高德地图页](https://modelscope.cn/mcp/servers/@amap/amap-maps)。
2. 点击「连接」，填入上面申请的高德 Key，生成专属 SSE 地址，形如：
   `https://mcp.api-inference.modelscope.net/<你的id>/sse`。
3. 如需鉴权，页面会同时给出 Token（通常用 ModelScope 的 API Key）。

| 优点 | 缺点 |
|---|---|
| 无需自建服务，页面一键生成 | 多一跳代理，稳定性取决于 ModelScope |
| Key 不落到你的服务器 | 生成的 URL 主要用于其试验场/调试 |

### 方式 B：高德官方直连（推荐生产使用）

```json
{
  "mcpServers": {
    "amap-maps": {
      "url": "https://mcp.amap.com/mcp?key=你的高德Key"
    }
  }
}
```

官方同时提供 Streamable HTTP（`/mcp`，推荐）与 SSE（`/sse`）两种端点。
官方文档：[快速接入高德地图 MCP Server](https://lbs.amap.com/api/mcp-server/gettingstarted)。

> 建议：**开发调试用方式 A，正式环境用方式 B**。两种方式在本模块里都支持，
> 只需改 `AMAP_MCP_URL` 一个配置项。

---

## 3. 后端配置

在 `backend/.env` 添加（参考 `backend/.env.example`）：

```env
# 高德开放平台 Web 服务 Key（两种方式都建议填）
AMAP_MAPS_API_KEY=你的高德Key
# MCP 地址：
#   留空 → 默认 https://mcp.amap.com/mcp?key=<AMAP_MAPS_API_KEY>（官方直连）
#   方式 A → 填 ModelScope 生成的 SSE 地址，例如：
#     https://mcp.api-inference.modelscope.net/<你的id>/sse
AMAP_MCP_URL=
# 可选：方式 A 连接 ModelScope 时需要的鉴权 Token
AMAP_MCP_AUTH_TOKEN=
```

新增依赖：`mcp>=1.20`（已加入 `backend/requirements.txt`）。

---

## 4. API 接口契约

所有接口前缀 `/api/v1`，需要 JWT（`Authorization: Bearer <token>`）。
未配置 Key 且未配置 `AMAP_MCP_URL` 时返回 `503`；上游 MCP 调用失败返回 `502`。

### 4.1 列出可用工具

```http
GET /api/v1/maps/tools
```

响应：

```json
{
  "tools": [
    {
      "name": "maps_weather",
      "description": "根据城市名称或者标准adcode查询指定城市的天气",
      "inputSchema": {
        "type": "object",
        "properties": { "city": { "type": "string", "description": "城市名称或者adcode" } },
        "required": ["city"]
      }
    }
  ]
}
```

### 4.2 通用工具调用

```http
POST /api/v1/maps/invoke
Content-Type: application/json
```

请求体：

```json
{ "tool": "maps_weather", "arguments": { "city": "北京" } }
```

响应统一结构：

```json
{ "tool": "maps_weather", "data": { "city": "北京市", "forecasts": [] } }
```

### 4.3 便捷端点

| 方法 | 路径 | 参数 | 对应工具 |
|---|---|---|---|
| GET | `/maps/geocode` | `address` 必填；`city` 可选 | `maps_geo` |
| GET | `/maps/regeocode` | `location`（经度,纬度）必填 | `maps_regeocode` |
| GET | `/maps/ip-location` | `ip` 必填 | `maps_ip_location` |
| GET | `/maps/weather` | `city`（城市名或 adcode）必填 | `maps_weather` |
| GET | `/maps/distance` | `origins` 必填（可多个，分号分隔）；`destination` 必填；`type` 可选 `0`直线/`1`驾车/`3`步行 | `maps_distance` |
| GET | `/maps/poi` | `keywords` 必填；`city`、`types` 可选 | `maps_text_search` |
| GET | `/maps/around` | `location`（经度,纬度）必填；`keywords`、`radius` 可选 | `maps_around_search` |
| GET | `/maps/poi/{poi_id}` | 路径参数 `poi_id` | `maps_search_detail` |
| GET | `/maps/route` | `origin`、`destination`（经度,纬度）必填；`mode` 可选 `driving`/`walking`/`bicycling`/`transit`；公交需 `city`、`cityd` | 对应路线工具 |

坐标统一为「经度,纬度」字符串，例如 `116.397428,39.90923`。

---

## 5. 完整工具清单

| 工具名 | 必填参数 | 说明 |
|---|---|---|
| `maps_geo` | `address` | 地址转经纬度，可选 `city` |
| `maps_regeocode` | `location` | 经纬度转行政区划地址 |
| `maps_ip_location` | `ip` | IP 定位 |
| `maps_weather` | `city` | 天气查询（城市名或 adcode） |
| `maps_distance` | `origins`, `destination` | 距离测量；`type`：`0` 直线 / `1` 驾车 / `3` 步行 |
| `maps_text_search` | `keywords` | 关键词搜 POI，可选 `city`、`types` |
| `maps_around_search` | `location` | 周边搜 POI，可选 `keywords`、`radius` |
| `maps_search_detail` | `id` | POI 详情 |
| `maps_direction_driving` | `origin`, `destination` | 驾车路线 |
| `maps_direction_walking` | `origin`, `destination` | 步行路线 |
| `maps_direction_bicycling` | `origin`, `destination` | 骑行路线 |
| `maps_direction_transit_integrated` | `origin`, `destination`, `city`, `cityd` | 公交/地铁路线 |
| `maps_schema_personal_map` | 视 schema 而定 | 生成高德个人地图 schema（攻略/点位导入高德 APP） |
| `maps_schema_navi` | 视 schema 而定 | 生成导航 schema |
| `maps_schema_take_taxi` | 视 schema 而定 | 生成打车 schema |

> 说明：实际线上 MCP Server 共暴露 **15 个工具**（含上表 12 个查询类 + 3 个 `maps_schema_*` 场景类）。
> 骑行工具名以 `maps_direction_bicycling` 为准。以 `GET /api/v1/maps/tools` 实时返回为准。

### 5.1 单个店铺的具体分类：`typecode`

MCP 的 POI 搜索（`maps_around_search` / `maps_text_search`）返回的每个店铺带 **`typecode`** 字段，即高德对该店铺的具体三级分类码，例如（武汉实测 2026-08）：

| 店铺 | typecode | 含义 |
|---|---|---|
| 某火锅店 | `050117` | 餐饮服务 → 中餐厅 → 火锅店 |
| 某烧烤店 | `050118` | 餐饮服务 → 中餐厅 → 特色/地方风味餐厅 |
| 某咖啡厅 | `050500` | 餐饮服务 → 咖啡厅 → 咖啡厅 |
| 麦当劳 | `050302` | 餐饮服务 → 快餐厅 → 麦当劳 |

要点：
- `typecode` 可能是多值，以 `|` 分隔（如 `050302|050900`），需拆分后逐个判断；
- MCP 返回的 POI 字段较精简（`id/name/address/typecode/photo`），**不含** Web API 的 `type` 文本字段；
- `maps_search_detail`（Web API 为 `/v3/place/detail`）可拿到更深的单店数据：`rating`（评分）、`cost`（人均）、`open_time/opentime2`（营业时间）、`business_area`（商圈名）；商圈分析已据此给竞品补深度数据（详见 SPEC-DISTRICT 2.4）；
- 商圈分析产品链路走 Web API（同时拿到 `type` + `typecode`），竞品判定即「type 文本子串 OR typecode 精确命中」，详见 [SPEC-DISTRICT.md](./SPEC-DISTRICT.md) 3.1。

---

## 6. 使用示例

### 6.1 天气查询（外卖运营参考）

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/maps/weather?city=上海"
```

```json
{
  "tool": "maps_weather",
  "data": {
    "city": "上海市",
    "forecasts": [
      { "date": "2026-08-04", "week": "2", "dayweather": "多云", "nightweather": "阴",
        "daytemp": "31", "nighttemp": "24", "daywind": "东南", "nightwind": "东南",
        "daypower": "3", "nightpower": "3", "daytemp_float": "31.0", "nighttemp_float": "24.0" }
    ]
  }
}
```

### 6.2 竞品/商圈搜索

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/maps/poi?keywords=%E7%81%AB%E9%94%85&city=%E6%88%90%E9%83%BD"
```

### 6.3 门店周边 3km 竞品密度

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/maps/around?location=104.065735,30.659462&keywords=%E5%A5%B6%E8%8C%B6&radius=3000"
```

### 6.4 配送距离估算

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/maps/distance?origins=104.065735,30.659462&destination=104.101756,30.636958&type=1"
```

---

## 7. 在其它 MCP 客户端中配置

### Codex / Claude / Cursor（官方直连）

```json
{
  "mcpServers": {
    "amap-maps": {
      "url": "https://mcp.amap.com/mcp?key=你的高德Key"
    }
  }
}
```

### ModelScope SSE 方式（stdio/SSE 客户端通用）

```json
{
  "mcpServers": {
    "amap-maps": {
      "type": "sse",
      "url": "https://mcp.api-inference.modelscope.net/<你的id>/sse"
    }
  }
}
```

如需鉴权，在客户端里为该 server 配置 `Authorization: Bearer <Token>` 请求头
（对应后端环境变量 `AMAP_MCP_AUTH_TOKEN`）。

### Node.js I/O（本地进程）方式

```json
{
  "mcpServers": {
    "amap-maps": {
      "command": "npx",
      "args": ["-y", "@amap/amap-maps-mcp-server"],
      "env": { "AMAP_MAPS_API_KEY": "你的高德Key" }
    }
  }
}
```

---

## 8. 测试

```bash
cd backend
pytest tests/test_amap_mcp.py -v
```

覆盖：服务层（URL 构建、结果解析、参数校验）+ API 层（鉴权 401、工具列举、
通用调用、天气便捷端点、未配置 503、上游失败 502）。测试 mock 掉 MCP 客户端，
不发起真实网络请求。

---

## 9. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `503 未配置高德 MCP` | `.env` 未填 Key 且未填 `AMAP_MCP_URL` | 补齐配置后重启后端 |
| `502 连接高德 MCP 失败` | 网络不通 / URL 写错 / 鉴权缺失 | 检查 `AMAP_MCP_URL` 与 `AMAP_MCP_AUTH_TOKEN`；国内环境直连官方地址即可 |
| `502 工具 xxx 执行失败：QUOTA_EXHAUSTED` | 高德 Key 当日免费额度用尽 | 控制台查看配额，或换 Key |
| `INVALID_USER_KEY` | Key 无效/类型不是 Web 服务 | 在开放平台检查 Key 类型与状态 |
| ModelScope SSE 连不上 | 生成的 URL 仅用于试验场 | 改用官方直连（方式 B） |

---

## 10. 参考链接

- ModelScope MCP 广场：<https://modelscope.cn/mcp/servers/@amap/amap-maps>
- 高德 MCP 官方文档：<https://lbs.amap.com/api/mcp-server/gettingstarted>
- 高德开放平台：<https://lbs.amap.com/>
- 官方 MCP Server 源码：<https://github.com/zxypro1/amap-maps-mcp-server>
