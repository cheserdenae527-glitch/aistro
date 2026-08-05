# AiRestro — 直播工坊模块 设计规约

> 版本：v0.6 · 2026-08-05
> 状态：定稿 · 自成一类模块
> 技术基线：数字人直播采用已调研的开源方案 lipku/LiveTalking + l11223/digital-human-livestream，详见 §3
> v0.5 变更：补充 avatar_id 跨 org 绑定校验；修正 source_script_id 描述中不会发生的分支；明确弹幕生成失败时旧配置保留不变
> v0.6 变更：engine_config 敏感字段 GET 脱敏要求写回 SPEC；补充 sessions PATCH 按状态限制可编辑字段（live 起锁定排期/绑定字段，终态仅 notes）

---

## 1. 模块定位

独立入口（侧边栏"直播工坊"）。面向代运营团队，把餐饮本地生活直播（以数字人辅助直播为主）从"临时拼凑"变成一条可执行的流水线：

```
直播间项目（门店 + 平台 + 时段 + 目标 + 优惠商品）
    │
    ▼
数字人形象（形象素材 + 声音 + 人设）
    │
    ▼
AI 生成直播脚本（开场/产品/优惠/互动/答疑/收尾 + 时长）
    │
    ▼
AI 生成弹幕互动规则（人设话术 + 回复规则 + 双向敏感词）
    │
    ▼
合规自检（AI 标识 / 人设审核 / 值守确认 / 敏感词复查）
    │
    ▼
人工确认 → 导出开播包（脚本 + 引擎配置 + 合规清单）
    │
    ▼
本地引擎开播（LiveTalking 推流 + 弹幕互动）
    │
    ▼
场次复盘（手动录入平台数据 + AI 复盘报告）
```

核心原则与口碑/装修板块一致：**AiRestro 只生产草稿与配置，不直接发布、不直接推流；真人运营确认后执行**。数字人引擎在本机/私有 GPU 环境部署，AiRestro 不嵌入渲染引擎。

> 合规底线：《直播电商监督管理办法》（2026-01-07 发布，2026-02-01 施行）与《人工智能拟人化互动服务管理暂行办法》（2026-07-15 施行）已生效，抖音等平台对数字人直播要求 AI 标识 + 真人值守。本模块强制 AI 标识、人设审核、值守确认、敏感词双向过滤，**不宣传、不出现"24 小时无人直播"等表述**。
>
> 适用范围提示：《人工智能拟人化互动服务管理暂行办法》第二条将"拟人化互动服务"界定为模拟自然人人格、持续性情感互动的服务，并明确智能客服等不涉及持续性情感互动的服务不适用。数字人直播带货的人设互动是否完全落入该办法监管范围，业内尚有讨论空间。本模块按"从严适用"处理（强制执行该办法的标识/退出等要求），但具体适用性以法务与平台最新指引为准，不作为法律结论。

---

## 2. 直播工作流

### 2.1 阶段

1. 策划：选门店/平台/时段/目标，录入直播优惠商品（MVP 手填；后续接团购工坊）
2. 准备：从形象库选数字人（或新建），确认人设
3. 脚本：AI 生成分段脚本 → 人工微调 → 合规自检 → 定稿
4. 互动：AI 生成弹幕回复规则 → 人工编辑确认（MVP 以"候选话术 + 人工粘贴"为主）
5. 开播：导出开播包 → 本地引擎启动 → 场次状态流转 + 值守确认
6. 复盘：手动录入平台数据 → AI 复盘

### 2.2 脚本结构（AI 强制输出）

| type | 中文 | 作用 | 建议时长 |
|---|---|---|---|
| opening | 开场留人 | 欢迎 + 今日福利预告 | 30-60s |
| product | 产品介绍 | 招牌菜/套餐逐个讲 | 每个 2-4min |
| promo | 优惠逼单 | 价格锚定 + 限量 + 倒计时 | 60-90s |
| interaction | 互动 | 问答/点菜/抽奖 | 穿插 |
| qa | 答疑 | 辣度/分量/配送/有效期 | 穿插 |
| closing | 收尾 | 核销引导 + 关注 + 下场预告 | 60s |

每段含 `cue`（画面/动作提示），用于 LiveTalking 动作编排与主播提示。

---

## 3. 技术选型与合规基线

### 3.1 开源引擎（本地/私有部署，均为 Apache-2.0）

| 组件 | 仓库 | 用途 | 要点 |
|---|---|---|---|
| LiveTalking | github.com/lipku/LiveTalking | 数字人视频实时生成 + 推流 | 支持 wav2lip/musetalk/ernerf 等模型；WebRTC/RTMP/虚拟摄像头输出；多 TTS（EdgeTTS/GPT-SoVITS/CosyVoice/腾讯云等）；动作编排；可自定义形象；GPU 要求 wav2lip ≥ RTX 3060、musetalk ≥ RTX 3080Ti |
| digital-human-livestream | github.com/l11223/digital-human-livestream | 弹幕互动 + 人设 + 双向过滤 + 管理后台 | 基于 LiveTalking 二次开发；DeepSeek 对话；B站弹幕采集（插件架构预留多平台）；persona.json + wordlist.txt 热加载；管理后台 API（persona/wordlist/直播控制/健康检查）；Docker 部署 |

### 3.2 集成方式（重要）

AiRestro 不内嵌渲染引擎、不直接推流，两者通过"开播包"对接：

- AiRestro 导出：脚本 Markdown + persona.json + wordlist.txt + 回复规则 + 合规清单 + 引擎启动说明
- 运营在本机/私有 GPU 环境运行 LiveTalking（推流到抖音/视频号/小红书等 RTMP），把 persona/wordlist 导入或通过管理后台 API 更新
- 弹幕自动回复：digital-human-livestream 原生支持 B站；**抖音/小红书/视频号不在 MVP 自动弹幕范围**（平台限制 + 合规风险），采用"AiRestro 生成候选话术 → 运营在直播间手动粘贴"的辅助模式
- LiveTalking 有开源声明：发布到 B站/视频号/抖音的视频需带 LiveTalking 水印与标识；该要求与 AI 标识合规方向一致，导出清单中必须保留提醒

### 3.3 合规基线（模块级强制项）

| 项 | 要求 |
|---|---|
| AI 标识 | 每个项目必须有 AI 标识文案（例："本直播间由 AI 数字人出镜，真人运营团队值守"），开播前确认 |
| 人设审核 | AI 生成人设不得冒充平台/官方，不得出现绝对化用语、医疗/效果承诺 |
| 值守确认 | 场次从 planned → live 必须 `duty_confirmed=true`（真人值守），未确认不允许进入开播状态 |
| 敏感词双向过滤 | 观众弹幕进入 AI 前过滤 + AI 回复发出前过滤；内置词库 + 项目自定义词库 |
| 话术红线 | 不宣传"无人直播/24 小时无人直播"；不引导站外私下交易（微信转账等） |
| 平台规则 | 导出包附带平台数字人直播规则提醒（各平台随时更新，以平台公告为准） |

---

## 4. 数据模型

### live_projects（直播项目）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| shop_id | UUID FK → shops | |
| title | varchar(100) | 项目名 |
| platform | enum douyin / xiaohongshu / wechat | 主直播平台（视频号 = wechat；后续扩展 bilibili 等） |
| goal | text nullable | 场次目标（曝光/互动/核销/GMV） |
| promo_items | jsonb | `[{ name, price, original_price, rules, link }]` 手填优惠商品，MVP 不接团购工坊 |
| ai_label_text | varchar(200) nullable | AI 标识文案（例："本直播间由 AI 数字人出镜，真人运营团队值守"）；LiveCompliance 检查"AI 标识文案存在"即检查此字段非空 |
| engine_config | jsonb nullable | `{ base_url, api_key?, enabled, last_health_check }` 本地引擎连接配置，L1 仅存储，L3 联调；**GET 响应中 `api_key` 等敏感字段脱敏**，不原样回传（仅返回是否已配置），见 §8 |
| status | enum draft / active / archived | |
| created_at / updated_at | timestamptz | |

> `ai_label_text` 首次创建项目时若为空，AI 生成脚本时按标准话术自动填充默认值，运营可在基本信息 Tab 修改；合规自检、`ai_label_confirmed` 均以此字段内容为准。

> 级联：删除 `live_projects` → `live_scripts` / `live_danmaku_configs` / `live_sessions`（→ `live_session_metrics`）全部 `ON DELETE CASCADE`。

### live_avatars（数字人形象库，团队级共享）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| org_id | UUID FK → orgs | 所属团队/组织（不是 shop）；同一账号下的多个门店共享，跨组织不可见 |
| name | varchar(100) | |
| avatar_type | enum image / video | 形象驱动类型 |
| image_url | text nullable | 形象图（MinIO） |
| video_url | text nullable | 驱动视频（MinIO） |
| voice_config | jsonb | `{ provider, voice, speed, pitch }`（映射 LiveTalking TTS 配置） |
| persona | jsonb | `{ identity, tone, boundaries, forbidden_topics }` |
| status | enum draft / ready / disabled | |
| created_at / updated_at | timestamptz | |

> 删除保护：被 `live_scripts` / `live_sessions` 引用时返回 409。
>
> **鉴权边界说明**：`live_avatars` 不挂 `shop_id`，而是挂 `org_id`（团队/组织维度）。这意味着 §6 开头"全部 JWT + shop 所有权校验"对 avatars 端点不完全适用——avatars 的读写改删校验的是"当前用户所属 org 是否匹配"，而不是 shop 所有权。若当前系统尚无 org/租户模型（只有 user → shop 的绑定关系），MVP 阶段可退化为 `org_id = 创建该形象的用户所绑定的主账号 ID`，效果等价于"同一账号下所有门店共享，其他账号不可见"；但**不能**退化成"任何登录用户都可以编辑/删除任何形象"，否则存在跨租户数据泄露与破坏风险。这一点在 G1 写鉴权中间件时必须显式测试覆盖。
>
> **凡是接受 `avatar_id` 作为入参的接口，必须校验该形象的 `org_id` 与当前用户一致**，否则一律 404（跨 org 一律当不存在处理，不区分 403/404，与其他跨租户场景保持一致）。这条校验适用但不限于：`scripts/generate` 的 `avatar_id`、`sessions` 创建/编辑（PATCH）时传入的 `avatar_id`。校验对象是 avatar 本身的 org 归属，不是发起请求的 shop——即便当前 shop 属于该用户，如果 avatar_id 指向别的 org，同样拒绝，避免别的团队的形象 persona/素材被跨组织带进本项目。G1 测试清单需覆盖"跨 org 传 avatar_id → 400/404"这一用例。

### live_scripts（直播脚本）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → live_projects | |
| avatar_id | UUID FK → live_avatars nullable | 生成时引用的人设来源 |
| persona_snapshot | jsonb nullable | 生成脚本那一刻从 `live_avatars.persona` 拷贝的快照；此后该形象的 persona 被编辑不会回溯影响本脚本。合规自检（§5.4）、confirm、export 的 persona 相关校验和导出内容一律以此字段为准，不实时查询 `live_avatars`；若 `avatar_id` 为空则本字段也为空，合规检查跳过人设相关项并在 items 中标注"未关联形象人设" |
| generation_batch | int | 第几次 generate |
| title | varchar(200) | |
| tone | varchar(50) | 风格（烟火气/专业/热情/治愈） |
| content | jsonb | 分段数组 `[{ type, title, text, duration_sec, cue }]`，type 见 §2.2 |
| total_duration_sec | int nullable | |
| status | enum draft / edited / confirmed | |
| is_archived | boolean default false | regenerate 时旧批次归档，不删除 |
| compliance | jsonb nullable | 合规自检快照 `{ pass, items: [{ key, ok, detail }] }` |
| created_at / updated_at | timestamptz | |

> confirm 语义：confirm 时若 `compliance.pass != true` → 422 拒绝；通过后 `status=confirmed`，幂等（已 confirmed 重复调用返回 200）。confirmed 不允许 PUT / DELETE（返回 400），只能通过 regenerate 归档。

### live_danmaku_configs（弹幕互动配置，一项目一条）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK unique | |
| source_script_id | UUID FK → live_scripts nullable | 生成本批弹幕规则时依据的脚本版本；export 时若该脚本 id 不等于当前导出的脚本 id（sid），在 compliance.items 追加提示"弹幕规则基于其他脚本版本生成，建议重新生成"（不阻断，与"未配置弹幕规则"同一处理方式）。脚本一旦归档即无法导出（见 §6 export），故不存在"弹幕基于已归档脚本"的导出场景 |
| persona | jsonb | 运营可微调的人设 |
| reply_rules | jsonb | `[{ trigger, reply, mode: auto/manual }]`；auto 仅限引擎支持平台（B站等），其余一律 manual |
| sensitive_words | jsonb | string[]，双向过滤，导出为 wordlist |
| escalate_topics | jsonb | string[]（投诉/价格争议/食品安全/优惠领取），命中必须转真人 |
| created_at / updated_at | timestamptz | |

> 与 `live_scripts` 不同，本表**不做版本归档**（一项目一条，regenerate 直接覆盖）。这是有意的简化：弹幕规则调整频率高、单条数据体量小，MVP 阶段不认为历史版本有留存必要；如后续需要审计追溯，再补 `is_archived` 批次模式。

### live_sessions（开播场次）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK → live_projects | |
| script_id | UUID FK → live_scripts nullable | 本次使用的脚本版本 |
| avatar_id | UUID FK → live_avatars nullable | |
| scheduled_at | timestamptz | |
| duration_min | int nullable | |
| status | enum planned / live / ended / cancelled | 状态机：planned → live → ended；planned → cancelled（终态）；planned → ended（事后补录，跳过 live 状态追踪，用于漏排期后补录已完成场次）；live 不可回退 |
| operator_id | UUID FK → users nullable | 值守人；`duty_confirmed=true` 时该字段必须非空（校验在 PATCH 状态流转时执行，否则 422） |
| duty_confirmed | boolean default false | planned → live 必须 true，否则 422；置为 true 时必须已填 operator_id |
| ai_label_confirmed | boolean default false | 同上，必须 true；确认的是 `live_projects.ai_label_text` 内容已核对无误 |
| is_backfilled | boolean default false | 通过 `planned → ended` 补录路径产生的场次自动置 true；GET 详情/列表需展示该标记，复盘统计时与正常走完 live 状态的场次区分展示，避免混淆"系统认可的合规开播"与"事后补记录" |
| notes | text nullable | |
| started_at / ended_at | timestamptz nullable | |
| created_at / updated_at | timestamptz | |

> **字段可编辑性与状态绑定**：`planned` 状态可修改排期/绑定字段（`script_id` / `avatar_id` / `scheduled_at` / `duration_min` / `operator_id` / `notes`）；进入 `live` 后 `script_id` / `avatar_id` / `scheduled_at` / `duration_min` 一律锁定（不允许把已开播场次中途换绑到别的脚本/形象），只允许改 `notes` 或流转到 `ended`；`ended` / `cancelled` 为终态，仅 `notes` 可改，任何排期/绑定/状态字段修改一律 400。详见 §6 PATCH 说明。

### live_session_metrics（场次复盘数据）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK → live_sessions | |
| metrics | jsonb | `{ viewers, peak_viewers, avg_watch_sec, interaction_count, danmaku_count, order_count, gmv, redemption_count, note }` |
| source | enum manual / import | MVP 仅 manual |
| ai_review | text nullable | AI 复盘结论（生成后写入） |
| created_at / updated_at | timestamptz | |

---

## 5. AI 能力

### 5.1 LiveScriptAgent（脚本生成）

输入：门店品类/价格带、平台、目标、promo_items、形象 persona、tone、duration_min
输出：分段脚本（§2.2 结构）+ 合规风险提示（绝对化用语、承诺、站外交易引导等）
约束：总时长与 duration_min 偏差 ≤10%；敏感词过滤；频控 60s

### 5.2 LiveDanmakuAgent（弹幕规则生成）

输入：人设 + 定稿脚本 + 平台
输出：reply_rules（优惠怎么领/辣度/分量/排队/有效期/地址等常见餐饮弹幕场景）、sensitive_words 补充、escalate_topics
约束：命中 escalate_topics 的规则 mode 强制 manual；敏感词过滤；频控 60s；**前置条件：项目必须存在当前活跃批次（未归档）的 confirmed 脚本，否则接口返回 400**（见 §6）

### 5.3 LiveReviewAgent（复盘）

输入：metrics + 脚本概要
输出：数据解读（峰值/停留/互动/GMV/核销）、异常点、下场改进建议
约束：频控 30s；metrics 已存在时可用

### 5.4 LiveCompliance（合规自检，规则引擎 + AI 辅助）

检查项（脚本定稿阶段，§3.3 中与内容相关的部分）：AI 标识文案存在（即 `live_projects.ai_label_text` 非空）、人设无绝对化/承诺（校验对象为 `live_scripts.persona_snapshot`，不查询 `live_avatars` 当前值，见 §4 说明）、内容无敏感词、无站外交易引导
返回：`{ pass, items }`

> 说明：§3.3 合规基线里的"值守确认"是**场次维度**的强制项（谁在这一场直播值守），而非脚本内容本身的问题，因此不放进脚本 confirm 的 compliance 检查，而是在 §6 `live_sessions` 的 `planned → live` 状态流转时硬性校验 `duty_confirmed && operator_id` 非空。脚本可以在还没有排任何场次时就先定稿。

---

## 6. API

全部 JWT + shop 所有权校验（跨用户一律 404），**唯一例外是 `live-avatars` 系列端点**：其读写改删校验的是 org 归属而非 shop 所有权，详见 §4 `live_avatars` 鉴权边界说明。

```
POST /api/v1/live-projects → 创建
GET  /api/v1/live-projects?shop_id=&page=&page_size=
GET  /api/v1/live-projects/{id}
PATCH /api/v1/live-projects/{id}
DELETE /api/v1/live-projects/{id}（级联）

POST /api/v1/live-avatars → 新建形象（团队级共享，不绑定 shop）
GET  /api/v1/live-avatars?page=&page_size=
GET  /api/v1/live-avatars/{id}
PATCH /api/v1/live-avatars/{id}
DELETE /api/v1/live-avatars/{id}（被 scripts/sessions 引用 → 409）

POST /api/v1/live-projects/{id}/scripts/generate
  → Body: { tone?, duration_min?, avatar_id? }
  → avatar_id 传入时校验其 org_id 与当前用户一致，否则 404（见 §4 avatar 鉴权边界说明）
  → avatar_id 未传时，默认取项目最近一次成功生成脚本使用过的 avatar_id；若该形象当前 status=disabled，跳过默认值并返回 400 提示需显式指定形象；项目从未生成过脚本则必须显式传 avatar_id，否则 400
  → AI 生成一套完整脚本；generation_batch + 1；旧批次全部 is_archived=true（已 edited/confirmed 同样归档，内容不代入）
  → 频控 60s（user+shop，成功才计入；422 敏感词/AI 格式错误不计入）
GET  /api/v1/live-projects/{id}/scripts?include_archived=
GET  /api/v1/live-projects/{id}/scripts/{sid}
PUT  /api/v1/live-projects/{id}/scripts/{sid} → 人工编辑，status=edited（confirmed 禁止 PUT → 400）
POST /api/v1/live-projects/{id}/scripts/{sid}/confirm
  → 先合规自检，pass=false → 422 附问题清单；通过 → confirmed（幂等）
DELETE /api/v1/live-projects/{id}/scripts/{sid}（confirmed → 400）
POST /api/v1/live-projects/{id}/scripts/{sid}/export
  → 仅当前活跃批次（`is_archived=false`）的 `confirmed` 脚本可导出；已归档脚本调用返回 400（"该脚本已归档，如需留档请通过 GET 查看，不支持导出开播包"）——与 §6 sessions 开播前置校验的口径统一，避免"能导出但不能拿去开播"的不一致
  → 返回开播包 { script_markdown, persona_json, wordlist, reply_rules, compliance, engine_guide }
  → `persona_json` 来源优先级：若项目存在 `live_danmaku_configs` 且其 `persona` 非空，用该值（运营可能已在弹幕 Tab 精调过）；否则回退用 `live_scripts.persona_snapshot`；两者都为空则 `persona_json` 返回默认占位人设并在 compliance.items 提示"未配置人设"
  → 若项目尚未生成过弹幕配置（无 live_danmaku_configs 记录），reply_rules 返回空数组、wordlist 仅含脚本自身敏感词校验产生的默认词库，并在 compliance.items 中追加一条提示"未配置弹幕互动规则"（不阻断导出，仅提示）
  → 若已有弹幕配置但其 `source_script_id` 不等于本次导出的脚本（sid），在 compliance.items 追加提示"弹幕规则基于其他脚本版本生成，建议重新生成"（不阻断——典型场景是脚本 regenerate 出新的活跃批次后，弹幕配置还没跟着重新生成，仍指向已归档的旧脚本）

POST /api/v1/live-projects/{id}/danmaku-config/generate
  → 前置条件：项目必须存在一个**当前活跃批次**（`is_archived=false`）的 `status=confirmed` 脚本，否则 400；已归档的 confirmed 脚本不算数——避免弹幕规则基于已被 regenerate 替换掉的旧脚本生成（见 §5.2）
  → 覆盖式生成（同批规则整体替换），写入生成时依据的脚本 id 到 `source_script_id`；生成失败（LLM 报错、敏感词 422、格式校验失败等）时**保留旧配置原样不变**，不做任何覆盖——覆盖只在 AI 成功返回且通过校验后一次性落库；频控 60s（独立 key，不与 scripts/generate 共用）
GET  /api/v1/live-projects/{id}/danmaku-config（未生成过 → 404）
PUT  /api/v1/live-projects/{id}/danmaku-config → 人工编辑
POST /api/v1/live-projects/{id}/compliance/check → 返回 { pass, items }（不落库；confirm 时才快照）

POST /api/v1/live-projects/{id}/sessions → 排期（Body 含 script_id/avatar_id/scheduled_at/duration_min；avatar_id 同样需校验 org_id 归属，否则 404，见 §4）
GET  /api/v1/live-projects/{id}/sessions?page=&page_size=
GET  /api/v1/live-projects/{id}/sessions/{sid}
PATCH /api/v1/live-projects/{id}/sessions/{sid}
  → 编辑排期信息 + 状态流转；可编辑字段受状态限制（防止已结束场次被改绑到其他脚本/形象，导致复盘数据与实际直播内容对不上）：
    · planned：可改 script_id / avatar_id / scheduled_at / duration_min / operator_id / notes，以及 duty_confirmed / ai_label_confirmed 与状态流转
    · live：script_id / avatar_id / scheduled_at / duration_min 一律锁定，只允许改 notes 或流转到 ended
    · ended / cancelled（终态）：只允许改 notes，任何排期/绑定/状态字段修改一律 400
  → 状态流转校验：
    planned → live：以下全部满足，否则 422（错误信息逐项列出未满足项）：
      · duty_confirmed == true 且 operator_id 非空
      · ai_label_confirmed == true
      · 若 session.script_id 非空，该脚本 status == confirmed（脚本已被后续 regenerate 归档也视为不满足，需重新指定当前活跃批次的 confirmed 脚本）
      > **有意的 MVP 弹性**：`script_id` 允许为空，此时不做脚本相关校验——即"不挂 AI 生成脚本、纯人工直播"的场次只需满足值守 + AI 标识两项即可开播。这不是漏校验，是刻意保留的口子：不是所有场次都必须走 AI 脚本流程（例如临时加场、纯人工发挥的场次）。若后续要求"必须先有定稿脚本才能开播"，需要单独提出并修改此处为强制关联。
    live → ended / planned → cancelled：合法
    planned → ended：事后补录路径，跳过上述 planned→live 的前置校验（承认场次已线下完成，仅用于补记录，不代表系统认可其合规流程）；Body 必须同时提供 `started_at` 与 `ended_at`（否则 422），并自动置 `is_backfilled=true`
    cancelled / ended 为终态
DELETE /api/v1/live-projects/{id}/sessions/{sid}（已 live/ended/cancelled → 400）

POST /api/v1/live-projects/{id}/sessions/{sid}/metrics → 手动录入
GET  /api/v1/live-projects/{id}/sessions/{sid}/metrics
POST /api/v1/live-projects/{id}/sessions/{sid}/review
  → AI 复盘写入 metrics.ai_review；频控 30s（key 为 user+session_id，不是 user+shop，避免同店连续复盘多场互相卡等待；成功才计入）；无 metrics → 400
```

### 开播包导出结构

```json
{
  "script_markdown": "## 开场留人（60s）\n...",
  "persona_json": {
    "name": "店长小雅",
    "personality": "亲切热情，懂美食",
    "style": "烟火气，口语化",
    "knowledge_scope": "本店菜品、优惠、营业信息",
    "forbidden_topics": ["政治", "宗教"]
  },
  "wordlist": ["敏感词1", "regex:加微信.*"],
  "reply_rules": [
    { "trigger": "优惠", "reply": "今日套餐 9.9 元起，点小黄车就能下单", "mode": "manual" }
  ],
  "compliance": { "pass": true, "items": [] },
  "engine_guide": "启动命令 + RTMP 地址 + 水印/AI 标识提醒"
}
```

`wordlist` / `persona_json` 与 digital-human-livestream 的 `config/` 结构对齐，可直接导入管理后台。

---

## 7. 前端

```
LiveIndexPage（/live）→ 项目列表 + 新建（选门店 + 平台 + 目标）
LiveEditorPage（/live/:id）
├─ Tab 基本信息（平台/目标/优惠商品/引擎连接配置）
├─ Tab 数字人形象（形象库选择 + 新建入口：名称/驱动素材/声音/人设）
├─ Tab 直播脚本
│   ├─ [生成脚本]（已有活跃批次或已定稿 → 二次确认"归档当前脚本"）
│   ├─ 分段卡片（按 type 分块，总时长 + 每段时长）
│   ├─ 逐段微调 + [合规自检]（不通过项高亮：命中敏感词、缺 AI 标识等）
│   ├─ [定稿]（compliance.pass=false 时禁用 + 显示原因）
│   └─ [导出开播包]（confirmed 才可用；导出页可复制/下载）
├─ Tab 弹幕互动
│   ├─ [AI 生成规则] → 人设 + 回复规则表（触发词→回复→模式）
│   ├─ 模式徽标：auto（仅引擎支持平台）/ manual（人工粘贴）
│   └─ 双向敏感词列表 + 转人工话题
└─ Tab 场次与复盘
    ├─ 场次列表 + 排期 + 状态流转（live/终态场次仅 notes 可编辑，排期/绑定字段禁用）
    ├─ planned → live 前置确认弹窗（值守人 + AI 标识文案确认）
    └─ 每场：录入复盘数据 → [AI 复盘]
```

---

## 8. 安全约束

| 接口 | 约束 |
|---|---|
| scripts/generate / danmaku-config/generate | 敏感词 422；频控 60s（user+shop，独立 key；成功才计入）；danmaku-config/generate 额外要求项目已有**当前活跃批次**的 confirmed 脚本，否则 400 |
| sessions/{sid}/review | 频控 30s（key=user+session_id，成功才计入） |
| confirm | compliance.pass=false → 422；幂等 |
| export | 仅当前活跃批次的 confirmed 脚本可导出；已归档 400；未定稿 400；未配置弹幕规则不阻断，导出包内提示 |
| sessions PATCH（planned→live） | duty_confirmed && operator_id 非空、ai_label_confirmed、关联脚本（若有）status=confirmed，任一不满足 → 422 |
| sessions PATCH 字段可编辑性 | 见 §6：live 起 script_id / avatar_id / scheduled_at / duration_min 锁定；ended / cancelled 终态仅 notes 可改 |
| engine_config GET 响应 | api_key 等敏感字段脱敏，不原样回传（仅返回是否已配置） |
| 形象删除 | 被 scripts/sessions 引用 → 409 |
| 形象读写改删 | 校验 org 归属（非 shop 维度，见 §4 live_avatars 鉴权边界说明） |
| avatar_id 入参（scripts/generate、sessions 创建/PATCH） | 校验该 avatar 的 org_id 与当前用户一致，跨 org 一律 404 |
| 全部文本字段 | 敏感词校验（脚本/人设/回复规则/notes） |

---

## 9. MVP 边界

### 包含

- 项目/形象/脚本/弹幕配置/场次/复盘全部 CRUD 与状态机
- AI 脚本生成 + 人工微调 + 合规自检 + 定稿 + 开播包导出
- AI 弹幕规则生成（人工确认后使用；辅助模式为主）
- 场次排期 + 状态流转 + 值守/AI 标识硬校验 + 手动复盘 + AI 复盘
- 本地引擎部署指南 + 开播包格式约定（L3）

### 不包含

- AiRestro 直接推流/控制直播间（本地引擎执行）
- 抖音/小红书/视频号弹幕自动抓取与自动回复（平台限制 + 合规风险；后续如引擎生态支持再评估）
- B站自动直播深度集成（digital-human-livestream 可选，单独里程碑）
- 平台直播数据自动回流（手动录入；后续爬虫/平台 API）
- 直播切片自动剪辑/二次分发（后续内容工坊扩展）
- 团购工坊自动取数（MVP 手填 promo_items；后续关联 deal_schemes）
- 多账号矩阵/批量开播调度

---

## 10. 复用清单

| 能力 | 来源 |
|---|---|
| DeepSeek LLM | `app.ai` 客户端模式 |
| JWT + shop 所有权 | `app.core.deps` + 现有 helper |
| MinIO（形象素材） | `app.services.storage` |
| 敏感词 / 频控 | `app.core` |
| 团购工坊 | 后续关联套餐方案与优惠 |
| 内容工坊 | 后续扩展切片/预告片 |

> **L1 开工前必须先确认**：现有 `users`/`shops` 模型是否已有 org/owner 一类的组织维度字段。若没有，需要和主项目团队对齐 `live_avatars.org_id`（见 §4）具体映射到哪个现有字段（例如账号主体 ID），并在迁移脚本里落实，而不是凭空建一个新的 org 表——这决定了 L1 的鉴权中间件怎么写，应作为 L1 第一个任务，写代码前先查清楚。