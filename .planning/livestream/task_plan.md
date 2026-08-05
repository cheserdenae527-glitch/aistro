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
