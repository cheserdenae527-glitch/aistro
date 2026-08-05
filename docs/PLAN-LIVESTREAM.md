# 直播工坊模块 — 实现计划

> 基于 SPEC-LIVESTREAM v0.6 · 独立于主项目里程碑

## 依赖与复用

| 能力 | 来源 | 状态 |
|---|---|---|
| DeepSeek LLM | `app.ai` 客户端模式 | 已有 |
| JWT + shop 所有权 | `app.core.deps` | 已有 |
| MinIO（形象素材） | `app.services.storage` | 已有 |
| 敏感词 / 频控 | `app.core` | 已有 |
| 开源引擎 | lipku/LiveTalking + l11223/digital-human-livestream（Apache-2.0） | L3 接入，不嵌入后端 |

---

## L1 — 后端：模型 + API + AI Agents

**目标**：直播项目/形象/脚本/弹幕配置/场次/复盘全部 API 可用，AI 脚本与弹幕规则生成、合规自检、开播包导出闭环。

### 任务清单

0. **开工前确认（SPEC §4 / §10 末尾）**：核对现有 `users`/`shops` 模型是否已有 org/owner 组织维度字段，确定 `live_avatars.org_id` 的映射来源（若没有则与主项目对齐为账号主体 ID，不凭空新建 org 表）；确认结果决定 L1 鉴权中间件的写法
1. Alembic 迁移：
   - live_projects / live_avatars / live_scripts / live_danmaku_configs / live_sessions / live_session_metrics
   - live_projects.ai_label_text（AI 标识文案，默认话术自动填充）
   - live_scripts.persona_snapshot（生成脚本时快照 persona，合规/confirm/export 一律用快照）
   - live_danmaku_configs.source_script_id（FK → live_scripts）+ 唯一约束 (project_id)
   - live_sessions.operator_id / is_backfilled
   - 级联：删除 live_projects → scripts / danmaku_configs / sessions（→ metrics）全级联
   - 枚举：platform、avatar_type、status 系列、session status、metrics source
2. SQLAlchemy 模型 + Pydantic Schema
3. API（见 SPEC §6 全量端点）：
   - scripts/generate：avatar_id 缺省取最近一次成功生成所用形象（disabled → 400 要求显式指定）；生成时写入 persona_snapshot；generation_batch+1，旧批次归档
   - danmaku-config/generate：前置必须存在**当前活跃批次（is_archived=false）**的 confirmed 脚本（已归档 confirmed 不算）；覆盖式生成并写 source_script_id；生成失败不覆盖旧配置
   - confirm：compliance 检查以 persona_snapshot 为准，pass=false → 422；幂等
   - export：仅当前活跃批次的 confirmed 脚本可导出（归档 → 400）；persona_json 优先级（danmaku persona → persona_snapshot → 默认占位+提示）；source_script_id 不匹配追加提示；未配置弹幕规则追加提示（均不阻断）
   - sessions：planned→live 硬校验（duty_confirmed && operator_id、ai_label_confirmed、script 若存在必须当前活跃 confirmed）；script_id 为空是**有意的 MVP 弹性**（纯人工直播）；planned→ended 补录必填 started_at/ended_at 并置 is_backfilled=true；终态不可逆；live 起 script_id/avatar_id/scheduled_at/duration_min 锁定，终态仅 notes 可改（SPEC §4/§6）
   - review：key=user+session_id，频控 30s
4. AI Agents：
   - LiveScriptAgent：分段脚本生成（§2.2 六类）+ 总时长偏差 ≤10% + 合规风险提示
   - LiveDanmakuAgent：回复规则 + 敏感词补充 + escalate_topics（命中 topic 的规则 mode 强制 manual）
   - LiveReviewAgent：复盘报告
   - LiveCompliance：规则检查（ai_label_text 非空、persona_snapshot 无绝对化/承诺、敏感词、站外交易引导）
5. 鉴权 / 频控（成功才计入）/ 敏感词：
   - scripts/generate、danmaku-config/generate：60s，user+shop，独立 key
   - sessions/{sid}/review：30s，key=user+session_id
   - live-avatars 系列：org 归属校验（非 shop 维度，SPEC §4 鉴权边界）
   - **avatar_id 绑定归属校验**：scripts/generate、sessions 创建/编辑时传入的 avatar_id 必须属于当前用户 org（跨 org → 404），防止把别的团队形象绑定到本项目导致 persona/素材跨租户泄露
   - engine_config.api_key 等敏感字段在 GET 响应中脱敏，不原样回传
6. 测试：
   - 脚本生成：6 类分段齐全、总时长偏差校验、敏感词 422 不占频控、AI 格式错误不占频控
   - persona 快照：生成后修改 live_avatars.persona 不影响脚本 compliance/export；avatar_id 为空时合规检查跳过人设项并标注
   - regenerate：旧批次归档（含 edited/confirmed）、新批次活跃、默认 avatar 回退（disabled → 400）
   - confirm：compliance.pass=false → 422；通过后 confirmed；幂等；confirmed 禁止 PUT/DELETE
   - export：未 confirmed → 400；**已归档 confirmed → 400**；persona_json 三态优先级；source_script_id 不匹配提示；未配置弹幕规则提示
   - danmaku generate：**已归档 confirmed 不算前置（400）**；覆盖写入 + source_script_id 正确；生成失败保留旧配置
   - 形象：org 归属鉴权（跨 org 404）、**跨 org avatar_id 绑定 404（scripts/generate / sessions 创建/PATCH）**、被 scripts/sessions 引用 → 409
   - 场次状态机：planned→live 逐项 422、无脚本场次允许开播（仅值守+AI 标识）、live→ended、planned→cancelled、planned→ended 补录（is_backfilled=true + 必填时间）、终态不可逆、已开播场次禁止 DELETE、live/终态禁止修改排期与绑定字段（仅 notes 可改）
   - review：无 metrics → 400、频控 key 粒度
   - 级联删除验证
   - 鉴权 401 / 跨用户 404 / 跨 org 404
7. 契约文档：`docs/contracts/livestream-api.md`
   - 状态机与 422 语义、confirm/export 前置条件（含归档禁止导出）
   - sessions PATCH 字段可编辑性（planned 可改、live 锁定、终态仅 notes）
   - 开播包 JSON 结构、persona_json 优先级、source_script_id 提示
   - persona/wordlist 对齐 digital-human-livestream `config/` 格式
   - 频控 key 粒度（scripts/danmaku 独立 user+shop、review user+session）
   - org 鉴权规则（avatars 与 avatar_id 绑定）与 shop 鉴权规则（其余）分列
   - LiveTalking 水印/AI 标识提醒必须出现在 engine_guide

### 交付物

- Swagger 可调用全部 API
- pytest 全绿 + 契约文档

---

## L2 — 前端直播工坊

**目标**：项目 → 形象 → 脚本 → 弹幕规则 → 合规 → 定稿 → 导出 → 场次复盘全流程可用。

```
前置：L1
```

### 任务清单

1. 路由 `/live` + `/live/:id`，侧边栏"直播工坊"入口
2. 项目列表（分页）+ 新建（选门店/平台/目标）
3. 数字人形象库：列表 + 新建/编辑表单（名称/驱动素材上传/声音/人设）；org 内共享
4. 直播脚本 Tab：
   - 生成脚本（已有活跃批次或已定稿 → 二次确认"归档当前脚本"）
   - 分段卡片（六类分块、总时长、逐段微调）
   - 合规自检（不通过项高亮，含"未关联形象人设"提示）+ 定稿（pass=false 禁用并显示原因）
   - 导出开播包（仅当前活跃批次的 confirmed 可用；归档脚本入口禁用；弹幕规则旧脚本/未配置提示展示）
5. 弹幕互动 Tab：AI 生成规则 → 回复规则表（触发词→回复→模式徽标）、双向敏感词、转人工话题
6. 场次与复盘 Tab：排期、状态流转（planned→live 前置确认弹窗：值守人 + AI 标识文案；无脚本开播允许并标注"纯人工直播"）、补录场次 is_backfilled 标记、复盘数据录入、AI 复盘
7. 联调真实 L1 API，先反查契约文档与 Swagger 是否一致，不一致以真实接口为准并回写文档
8. 前端测试：状态流转前置校验、定稿/导出按钮禁用逻辑、regenerate 二次确认、补录表单必填校验

### 交付物

- 全流程可用，真实 API 联调通过
- 前端构建 + 关键状态逻辑单测通过

---

## L3 — 本地引擎接入（文档 + 验证）

**目标**：开播包能真实驱动本地数字人引擎。

```
前置：L2
```

### 任务清单

1. 核实 LiveTalking / digital-human-livestream 最新部署方式（以实际仓库 README 为准），编写 `deploy/livestream/README.md`：
   - Windows / Ubuntu + GPU 要求（wav2lip ≥ RTX 3060、musetalk ≥ RTX 3080Ti）
   - RTMP / WebRTC / 虚拟摄像头输出配置
   - LiveTalking 水印与 AI 标识提醒
   - digital-human-livestream 管理后台与 Docker 部署
2. 开播包 JSON Schema 落地 `docs/contracts/livestream-bundle.schema.json`
3. 引擎管理后台 API 对接验证（`/health`、`/admin/persona`、`/admin/wordlist`）：
   - 可选：live_projects.engine_config 的"连接测试"功能（base_url + 健康检查 + 配置推送）
4. 端到端验证：导出开播包 → 本地引擎导入 persona/wordlist → 推流（有 GPU 环境时）；无 GPU 环境时验证到"配置导入成功 + 健康检查通过"
5. 合规文案终审：全模块不出现"无人直播/24 小时无人直播"宣传；导出包保留 LiveTalking 水印提醒

### 交付物

- 部署文档 + JSON Schema + 连接测试通过记录

---

## 风险与开放问题

- 抖音/小红书/视频号自动弹幕不可用 → 辅助模式（人工粘贴候选话术）；后续如需自动化，单独评估平台合规与引擎插件生态
- 平台数字人直播规则持续变化 → 导出包附"以平台最新公告为准"提醒
- GPU 硬件门槛 → 文档写明最低要求；无本地 GPU 可用云 GPU（AutoDL 等）
- LiveTalking 水印/标识要求与 AI 标识合规叠加 → 导出清单必须保留提醒
- 两个开源仓库版本迭代较快 → L3 部署指南以实际仓库为准，固定验证时的 commit
- 无脚本开播是刻意保留的 MVP 弹性（纯人工直播），不是漏校验；若后续收紧为强制关联需单独提出