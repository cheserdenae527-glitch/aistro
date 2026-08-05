# Livestream L1 — 后端：模型 + API + AI Agents（task plan）

> 依据 docs/PLAN-LIVESTREAM.md L1 / SPEC-LIVESTREAM v0.6

## 步骤
- [x] 0. 开工前确认：users/shops 无 org 维度 → org_id = 创建用户主账号（users.id）
- [x] 1. Alembic 迁移：6 张表 + 枚举 + 级联 + 唯一约束
- [x] 2. SQLAlchemy 模型 + Pydantic Schema
- [x] 3. API 全量端点（scripts/danmaku/sessions/review/export 状态机与前置校验）
- [x] 4. AI Agents（LiveScriptAgent/LiveDanmakuAgent/LiveReviewAgent/LiveCompliance）
- [x] 5. 鉴权（org/shop 分界）+ 频控（60s/30s 独立 key）+ 敏感词 + engine_config 脱敏
- [x] 6. pytest 全绿（状态机/批次/合规/export/org 鉴权/级联/频控）
- [x] 7. 契约文档 docs/contracts/livestream-api.md


## L2 — 前端直播工坊
- [x] 路由 /live + /live/:id + 侧边栏入口
- [x] 项目列表（商家/门店分组）+ 新建（选门店/平台/目标）
- [x] 数字人形象库（org 共享）：列表 + 新建/编辑（名称/素材/声音/人设）
- [x] 直播脚本 Tab：生成（归档二次确认）/分段微调/合规自检/定稿（pass=false 禁用）/导出开播包（归档禁用）
- [x] 弹幕互动 Tab：AI 生成 → 回复规则表 + 模式徽标 + 双向敏感词 + 转人工话题
- [x] 场次与复盘 Tab：排期/状态流转（开播前置确认弹窗）/补录标记/复盘录入 + AI 复盘
- [x] 联调真实 L1 API（dev 后端在线）
- [x] 前端测试：状态流转前置校验/定稿导出禁用/regenerate 二次确认/补录必填

## L3 — 本地引擎接入（文档 + 验证）
- [x] 核实 LiveTalking / digital-human-livestream 最新部署方式（固定 commit：c963ad4 / db728c7）
- [x] deploy/livestream/README.md：Windows/Ubuntu + GPU 要求 + RTMP/WebRTC/虚拟摄像头 + 水印/AI 标识提醒 + 管理后台与 Docker
- [x] docs/contracts/livestream-bundle.schema.json（draft-2020-12，样例校验通过）
- [x] 后端 engine-test 连接测试 API（健康检查 + persona/wordlist 推送 + last_health_check）+ pytest 12 项
- [x] 前端「连接测试」按钮 + liveService.engineTest + vitest 4 项
- [x] 契约文档 livestream-api.md 增补 engine-test
- [x] 端到端验证：mock 引擎（:8010）→ 健康检查 + 配置导入 + 热加载回读 + 覆盖地址 502；开播包 JSON Schema 校验
- [x] 合规终审：无「无人直播」宣传；导出包保留 LiveTalking 水印提醒（test_live.py:823）
