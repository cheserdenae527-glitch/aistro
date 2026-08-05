# Livestream L1 Findings

- users 模型：id/email/password_hash/name/role —— 无 org/租户字段。
- merchant.user_id → user；shop.merchant_id → merchant；无主账号/组织表。
- SPEC §4/§10 结论：MVP 退化 org_id = 创建形象的用户主账号 ID（users.id），效果=同账号门店共享、跨账号不可见；不新建 org 表。
- 鉴权边界：live-avatars 系列按 org（user.id）校验；live-projects/sessions/scripts 按 shop→merchant→user 校验；avatar_id 入参一律校验 org 归属（跨 org 404）。
- 频控：scripts/generate 与 danmaku-config/generate 独立 key（user+shop, 60s）；review user+session（30s）；成功才计入。
- export 前置：仅当前活跃批次（is_archived=false）confirmed；已归档 confirmed → 400。
- danmaku generate 前置：存在活跃批次 confirmed 脚本，否则 400；生成失败保留旧配置。
