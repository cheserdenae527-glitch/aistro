# 直播工坊 API 接口契约

> 版本：v1.0 · 2026-08-05（L1 交付）
> 基于：SPEC-LIVESTREAM v0.6 · PLAN-LIVESTREAM L1
> 状态：与后端真实接口逐条核对（L2 前端联调时以真实 Swagger 为准，不一致回写本文档）

## 通用约定

- **Base URL**: `/api/v1`
- **鉴权**: 全部端点需 `Authorization: Bearer <JWT>`；未带/无效 token → 401
- **分页**: `page` 默认 1（≥1）；`page_size` 默认 20，上限 100；响应 `{ items, total, page, size }`
- **敏感词**: 所有文本字段（标题/目标/AI 标识/优惠商品/人设/回复规则/敏感词/notes/engine_config 等）命中内置词库 → 422
- **归属校验链**（shop 维度）: `/live-projects/{id}/...` 资源校验 `project -> shop -> merchant -> user`，跨用户一律 404
- **org 鉴权（唯一例外）**: `/live-avatars` 系列端点校验 org 归属而非 shop 所有权，详见 §3
- **avatar_id 入参**: 凡接受 `avatar_id` 的接口（`scripts/generate`、`sessions` 创建/PATCH）都校验该形象 `org_id == 当前用户 id`，跨 org 一律 404

### 频控（成功才计入）

| 接口 | 窗口 | key 粒度 |
|---|---|---|
| `scripts/generate` | 60s | `live:scripts:generate:{user}:{shop}`（独立 key） |
| `danmaku-config/generate` | 60s | `live:danmaku:generate:{user}:{shop}`（独立 key，不与 scripts 共用） |
| `sessions/{sid}/review` | 30s | `live:review:{user}:{session_id}`（同店多场互不卡等待） |

- 触发限流 → 429；**敏感词 422 / AI 格式错误 502 不计入窗口**（仅成功落库后写 key）

### 状态枚举

- project `platform`: `douyin | xiaohongshu | wechat`；`status`: `draft | active | archived`
- avatar `avatar_type`: `image | video`；`status`: `draft | ready | disabled`
- script `status`: `draft | edited | confirmed`；`is_archived`: bool（批次归档）
- session `status`: `planned | live | ended | cancelled`
- metrics `source`: `manual | import`（MVP 仅 manual）

---

## 1. 直播项目

### POST /live-projects
Body：
```json
{
  "shop_id": "uuid",
  "title": "火锅直播间",
  "platform": "douyin",
  "goal": "提升核销",
  "promo_items": [{"name": "双人餐", "price": 88, "original_price": 128, "rules": "限时", "link": ""}],
  "ai_label_text": "本直播间由 AI 数字人出镜，真人运营团队值守",
  "engine_config": {"base_url": "http://localhost:12345", "api_key": "sk-xxx", "enabled": true}
}
```
- `platform` 默认 `douyin`；`status` 默认 `draft`
- `shop_id` 非本人门店 → 404；敏感词 422
- `engine_config` 敏感字段（`api_key`/`secret`）允许写入，但 **GET 响应一律脱敏**：不原样回传，仅返回 `api_key_configured: bool`

### GET /live-projects?shop_id=&page=&page_size=
当前用户全部项目（可按 shop_id 过滤），按 `updated_at` 倒序。

### GET /live-projects/{id}
`engine_config` 脱敏返回：
```json
"engine_config": {"base_url": "http://localhost:12345", "enabled": true, "api_key_configured": true}
```

### PATCH /live-projects/{id}
Body 任意子集：`title` / `platform` / `goal` / `promo_items` / `ai_label_text` / `engine_config` / `status`（敏感词 422）。
- `ai_label_text` 为空时，`scripts/generate` 会按标准话术自动填充默认值，运营可在此修改

### DELETE /live-projects/{id}
**级联删除** scripts / danmaku_configs / sessions（→ metrics），DB `ON DELETE CASCADE`；形象为 org 维度，不随项目删除。

### POST /live-projects/{id}/engine-test（L3 本地引擎连接测试）
**目标**：对本地数字人引擎执行健康检查 + 配置推送，验证「开播包 → 引擎」链路连通。

Body（全可选）：
```json
{
  "base_url": "http://localhost:8010",
  "push_persona": true,
  "push_wordlist": true,
  "persona_json": { "name": "店长小雅", "personality": "亲切热情", "style": "烟火气", "knowledge_scope": "本店信息", "forbidden_topics": ["政治", "宗教"] },
  "wordlist": ["加微信", "regex:广告\\d+"]
}
```

- `base_url`：可覆盖项目已存 `engine_config.base_url`（前端测试未保存的表单地址）；不传则用项目配置。均需以 `http://` / `https://` 开头，否则 400
- `push_persona` / `push_wordlist`：默认 true；为 false 时跳过对应推送
- `persona_json` / `wordlist`：显式覆盖推送内容；不传时按开播包导出同款优先级解析
  - persona：`live_danmaku_configs.persona` → 当前活跃批次 confirmed 脚本 `persona_snapshot` → 默认占位人设；推送前做引擎字段归一化（同导出，见 §7）
  - wordlist：`danmaku.sensitive_words` → 内置词库（红线话术 + 站外交易引导词）

执行流程（超时 15s）：
1. `GET {base_url}/health` — 非 2xx / 连接失败 → **502**（不更新 last_health_check）
2. `POST {base_url}/admin/persona` — 非 404 失败 → **502**
3. `POST {base_url}/admin/wordlist` — 非 404 失败 → **502**
4. 引擎未提供 `/admin` API（HTTP 404，纯 LiveTalking 场景）→ 推送标记 `skipped`，不阻断
5. 全部通过 → 200，写回 `engine_config.last_health_check`（UTC ISO）；`base_url` 为覆盖值时不写回（不污染项目配置）

**推送格式（2026-08-05 对真实 digital-human-livestream 实测校准）**：
- `persona`：以 `{name, personality, style, knowledge_scope, forbidden_topics}` 字典直接 POST；引擎四字段（name/personality/style/knowledge_scope）**必填非空**，缺失时 engine-test 自动兜底填充
- `wordlist`：**`{"content": "每行一词\nregex:xxx"}`**（真实 `admin.py` 要求 content 文本字段；仓库 README 的 JSON 数组示例与实际实现不符，以实现为准）

成功响应：
```json
{
  "ok": true,
  "base_url": "http://localhost:8010",
  "health": { "ok": true, "status_code": 200, "latency_ms": 12, "detail": "ok" },
  "persona_push": { "status": "ok", "detail": "..." },
  "wordlist_push": { "status": "skipped", "detail": "引擎未提供 /admin 接口（HTTP 404）..." },
  "last_health_check": "2026-08-05T04:00:00+00:00"
}
```

- `api_key` 已配置时以 `Authorization: Bearer <api_key>` 头发送（引擎无需鉴权时无副作用）
- 前端「基本信息」Tab 提供「连接测试」按钮，直接调用本接口并展示健康检查 / 人设推送 / 敏感词推送结果

---

## 2. 数字人形象（org 维度）

> **鉴权边界**：`live_avatars` 不挂 `shop_id`，挂 `org_id`。当前系统无 org/租户模型，MVP 按 SPEC §4/§10 退化为 `org_id = 创建该形象的用户主账号 ID（users.id）`：同账号下所有门店共享，跨账号不可见。读写改删一律校验 `org_id == 当前用户 id`，跨 org 一律 404（不区分 403/404）。

### POST /live-avatars
Body：
```json
{
  "name": "店长小雅",
  "avatar_type": "image",
  "image_url": null,
  "video_url": null,
  "voice_config": {"provider": "edge-tts", "voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0, "pitch": 0},
  "persona": {"identity": "店长小雅", "tone": "亲切热情，懂美食", "boundaries": "不承诺疗效", "forbidden_topics": ["政治", "宗教"]},
  "status": "draft"
}
```
- `org_id` 由服务端写为当前用户 id，客户端不可指定
- 敏感词 422（文本字段 + persona/voice_config 递归校验）

### GET /live-avatars?page=&page_size=
仅当前 org 可见。

### GET /live-avatars/{id} ｜ PATCH /live-avatars/{id}
跨 org → 404。

### DELETE /live-avatars/{id}
- 被 `live_scripts` 或 `live_sessions` 引用 → **409**（解除引用后可删）

---

## 3. 直播脚本

### POST /live-projects/{id}/scripts/generate
Body：`{ "tone"?, "duration_min"?, "avatar_id"? }`
- `avatar_id` 传入 → 校验 org 归属，跨 org 404
- `avatar_id` 未传 → 默认取最近一次成功生成脚本使用过的形象：
  - 该形象当前 `status=disabled` → 400「默认形象已停用，请显式指定」
  - 项目从未生成过脚本 → 400「请显式指定 avatar_id」
- 每次生成：`generation_batch + 1`，旧批次全部 `is_archived=true`（已 edited/confirmed 同样归档，内容不代入）
- 生成时写入 `persona_snapshot`（从 avatar.persona 拷贝，此后改形象不影响本脚本）
- `ai_label_text` 为空时自动填充默认值
- AI 输出校验：6 类分段（opening/product/promo/interaction/qa/closing）齐全、总时长与 `duration_min` 偏差 ≤10%、敏感词过滤
- 频控 60s；敏感词 422 / AI 格式错误 502 均不占窗口

### GET /live-projects/{id}/scripts?include_archived=
默认只返回当前活跃批次（`is_archived=false`），按 `generation_batch` 倒序；`include_archived=true` 返回全部。

### GET /live-projects/{id}/scripts/{sid}
### PUT /live-projects/{id}/scripts/{sid}
- 人工编辑 `title` / `tone` / `content` / `total_duration_sec`，自动置 `status=edited`（传 content 时按分段重算总时长）
- **confirmed 禁止 PUT → 400**

### POST /live-projects/{id}/scripts/{sid}/confirm
- 先合规自检（LiveCompliance）：AI 标识文案存在、人设（基于 `persona_snapshot` 快照）无绝对化/承诺、内容无敏感词/红线话术、无站外交易引导
- `pass=false` → **422**，`detail` 为 `{ message: "合规自检未通过", items: [{key, ok, detail}] }`
- 通过 → `status=confirmed` 并快照 `compliance`；**幂等**（已 confirmed 重复调用返回 200）
- 说明：值守确认是场次维度强制项，不放进脚本 confirm（脚本可先定稿再排场次）

### DELETE /live-projects/{id}/scripts/{sid}
- **confirmed → 400**；被场次引用 → 409

### POST /live-projects/{id}/scripts/{sid}/export
仅**当前活跃批次（`is_archived=false`）的 confirmed 脚本**可导出：
- 已归档（即使 confirmed）→ 400「该脚本已归档，如需留档请通过 GET 查看，不支持导出开播包」
- 未定稿 → 400
返回开播包（见 §7），`persona_json` 优先级：
1. `live_danmaku_configs.persona` 非空 → 用它（运营可能在弹幕 Tab 精调过）
2. 否则 `live_scripts.persona_snapshot`
3. 两者皆空 → 默认占位人设 + compliance.items 追加 `persona_placeholder` 提示
`compliance.items` 追加提示（均 `ok=true` 不阻断）：
- 无弹幕配置 → `danmaku_missing`「未配置弹幕互动规则」
- 弹幕配置 `source_script_id != sid` → `danmaku_stale`「弹幕规则基于其他脚本版本生成，建议重新生成」

---

## 4. 弹幕互动配置（一项目一条）

### POST /live-projects/{id}/danmaku-config/generate
- **前置条件**：项目必须存在**当前活跃批次（`is_archived=false`）**的 `confirmed` 脚本，否则 400；已归档的 confirmed 不算数
- 覆盖式生成（同批规则整体替换），写入 `source_script_id` = 生成时依据的脚本 id
- **生成失败（LLM 报错 / 敏感词 422 / 格式校验失败）时旧配置原样保留**，不做任何覆盖
- 频控 60s（独立 key）；仅成功落库后计入

### GET /live-projects/{id}/danmaku-config
未生成过 → 404。

### PUT /live-projects/{id}/danmaku-config
人工编辑 `persona` / `reply_rules` / `sensitive_words` / `escalate_topics`；未生成过则创建（`source_script_id` 为空）。编辑保留 `source_script_id`。
- `reply_rules[i]`: `{ trigger, reply, mode: "auto"|"manual" }`；`mode=auto` 仅限引擎支持平台（B站等），MVP 平台一律 manual

---

## 5. 合规自检

### POST /live-projects/{id}/compliance/check
Body：`{ "script_id"? }`（缺省取最新脚本；无脚本 → 400）
返回 `{ pass, items: [{ key, ok, detail }] }`，**不落库**（confirm 时才快照）。
- `key`: `ai_label` / `persona` / `sensitive` / `off_platform`
- 人设校验以 `persona_snapshot` 为准（不实时查形象）；快照为空 → `persona` 项 `ok=true` 并标注「未关联形象人设，跳过人设审核」
- `sensitive` 项同时覆盖红线话术（无人直播/24小时无人直播 等）

---

## 6. 场次与复盘

### POST /live-projects/{id}/sessions
Body：`{ script_id?, avatar_id?, scheduled_at, duration_min?, operator_id?, notes? }`
- `scheduled_at` 必填；`script_id` 必须属于本项目（否则 404）；`avatar_id` 校验 org 归属（跨 org 404）；`operator_id` 必须是存在的用户（否则 404）
- 创建即 `status=planned`，`duty_confirmed/ai_label_confirmed/is_backfilled=false`

### GET /live-projects/{id}/sessions?page=&page_size=
按 `scheduled_at` 倒序。

### GET /live-projects/{id}/sessions/{sid}

### PATCH /live-projects/{id}/sessions/{sid}
Body 任意子集：`script_id` / `avatar_id` / `scheduled_at` / `duration_min` / `operator_id` / `notes` / `duty_confirmed` / `ai_label_confirmed` / `status` / `started_at` / `ended_at`

**字段可编辑性（按状态）**：
| 状态 | 可改 | 禁止 |
|---|---|---|
| planned | script_id / avatar_id / scheduled_at / duration_min / operator_id / notes / duty_confirmed / ai_label_confirmed + 状态流转 | 其他字段 |
| live | 仅 notes + 流转到 ended | script_id / avatar_id / scheduled_at / duration_min（锁定）等 → 400 |
| ended / cancelled（终态） | 仅 notes | 任何排期/绑定/状态字段 → 400 |

**状态流转校验**：
- `planned → live`：以下全部满足，否则 422（`detail.items` 逐项列出未满足项）：
  - `duty_confirmed == true` 且 `operator_id` 非空（置 duty_confirmed=true 时也必须已填 operator_id）
  - `ai_label_confirmed == true`
  - 若 `script_id` 非空，该脚本必须是**当前活跃批次**的 `confirmed`（已被 regenerate 归档也视为不满足）
  - **有意的 MVP 弹性**：`script_id` 允许为空 → 纯人工直播场次只需满足值守 + AI 标识两项即可开播
- `planned → cancelled`：合法（终态）
- `live → ended`：合法
- `planned → ended`：**事后补录路径**，跳过 planned→live 前置校验；Body 必须同时提供 `started_at` 与 `ended_at`（否则 422），自动置 `is_backfilled=true`
- 非法流转 / 终态再流转 → 400

### DELETE /live-projects/{id}/sessions/{sid}
仅 `planned` 可删；live / ended / cancelled → 400。

### POST /live-projects/{id}/sessions/{sid}/metrics
手动录入复盘数据（每场一条，重复提交**覆盖**）：
Body：`{ "metrics": { viewers, peak_viewers, avg_watch_sec, interaction_count, danmaku_count, order_count, gmv, redemption_count, note }, "source": "manual" }`

### GET /live-projects/{id}/sessions/{sid}/metrics
无数据 → 404。

### POST /live-projects/{id}/sessions/{sid}/review
- 无 metrics → 400「该场次暂无复盘数据」
- AI 复盘写入 `metrics.ai_review`，返回 `{ ai_review }`
- 频控 30s，key = `user + session_id`；成功才计入

---

## 7. 开播包导出结构

```json
{
  "script_markdown": "# 夏日招牌直播脚本\n## 开场留人（60s）\n...",
  "persona_json": {
    "name": "店长小雅",
    "personality": "亲切热情，懂美食",
    "style": "烟火气，口语化",
    "knowledge_scope": "本店菜品、优惠、营业信息",
    "forbidden_topics": ["政治", "宗教"]
  },
  "wordlist": ["敏感词1", "加微信", "regex:加微信.*"],
  "reply_rules": [
    { "trigger": "优惠", "reply": "今日套餐 9.9 元起，点小黄车就能下单", "mode": "manual" }
  ],
  "compliance": { "pass": true, "items": [] },
  "engine_guide": "启动命令 + RTMP 地址 + 水印/AI 标识提醒"
}
```

- `wordlist` / `persona_json` 与 digital-human-livestream `config/` 结构对齐，可直接导入管理后台
- `persona_json` 字段归一化：来源人设若为形象风格字段（`identity/tone/boundaries`），导出时映射补充引擎字段（`name`←`identity`、`style`←`tone`）并**保留原字段**，保证引擎可读且不丢原始信息；已是引擎格式（含 `name/personality/style/knowledge_scope` 任一）则原样返回
- `wordlist`：已配置弹幕规则 → `danmaku.sensitive_words`；未配置 → 内置词库 + 红线话术 + 站外交易引导词
- 前端导出弹窗支持「下载引擎文件」（persona.json / wordlist.txt / script.md / reply_rules.json / engine_guide.txt）与「下载开播包」（完整 JSON），可直接灌入引擎
- `engine_guide` 固定包含：LiveTalking 启动/RTMP 推流指引、persona/wordlist 导入路径、**LiveTalking 水印提醒**、**AI 标识文案提醒**、平台规则以最新公告为准

---

## 8. 安全约束速查

| 接口 | 约束 |
|---|---|
| scripts/generate / danmaku-config/generate | 敏感词 422；频控 60s（user+shop，独立 key，成功才计入） |
| sessions/{sid}/review | 频控 30s（user+session_id，成功才计入）；无 metrics 400 |
| confirm | compliance.pass=false → 422（附 items）；幂等 |
| export | 仅当前活跃批次 confirmed；已归档 400；未定稿 400 |
| sessions PATCH（planned→live） | 值守/AI 标识/脚本前置任一不满足 → 422 逐项列出 |
| sessions PATCH 字段可编辑性 | live 起排期/绑定字段锁定；终态仅 notes |
| engine_config GET | api_key 等脱敏，仅返回 api_key_configured |
| engine-test | 未配置/非法 base_url 400；健康检查或配置推送失败（非 404）→ 502；仅通过后写回 last_health_check |
| 形象删除 | 被 scripts/sessions 引用 → 409 |
| 形象读写改删 / avatar_id 入参 | org 归属校验，跨 org 一律 404 |
| 全部文本字段 | 敏感词校验（脚本/人设/回复规则/notes/engine_config） |

> **合规口径**：本模块不宣传「无人直播/24小时无人直播」；导出的 engine_guide 必须保留 LiveTalking 水印与 AI 标识提醒。平台数字人直播规则随时更新，以平台最新公告为准。
