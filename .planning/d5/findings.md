# D5 Findings

- 文字拖拽用 replace 更新不会清 future，导致撤销后重做栈脏；需在拖拽结束提交历史节点。
- 前端 zustand 已有依赖，可直接做全局 job store；axios promise 在组件卸载后仍会完成，静态 notification 可弹出。
- 提示词可重复：Redis 缓存 key = focus + dish_name，LLM temperature 调低。