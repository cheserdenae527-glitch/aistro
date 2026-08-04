# D9 Findings

- 分页 Agent 校验过严会 502：LLM 返回越界 image_index 或超短标题时，应降级（纯文字页/截断）而非整单失败；视觉质量交给 QA。
- 测试 hermetic：多个 enrich 测试的 _make_copy 未 stub 文案 Agent，会走真实 DeepSeek（挂起/波动）；已统一 stub。
- asyncpg InvalidCachedStatementError / 重复注册：测试库被多次中断会话后出现的瞬时环境问题，干净重跑即恢复。
- 真实素材建议：视觉设计素材库 active + AI pending 候选混用；装修品牌色与工坊杂志色板定位不同，需映射而非替换。
