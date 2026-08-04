# D6 Progress

## 2026-08-04
- 开始视觉设计工程补强。

## 2026-08-04 实现
- 后台异步任务：design_jobs + 4 个 job 创建接口 + GET 轮询；前端 store.trackJob 轮询并通知。
- 缩略图：上传/生成/保存自动生成 320px JPEG thumb_url。
- GC：cleanup-discarded 删除废弃候选 + MinIO 对象。
- 菜单历史：menu_design_versions 快照（创建/更新/渲染写入），GET versions + restore，前端版本历史弹窗。
- 验证：design 35 passed；前端 15 tests + build；Playwright 版本历史弹窗通过；迁移已应用。