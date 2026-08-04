# D6 — 视觉设计工程补强（task plan）

## 步骤

### 1. 后端异步生图任务
- [x] design_jobs 表 + 迁移 a9c1d2e3f4a5
- [x] 异步任务执行器（generate / ai-beautify / bg-replace / enhance）
- [x] POST .../jobs 202 + GET 轮询接口
- [x] 前端改用 job 轮询 + 通知

### 2. 缩略图
- [x] 上传/生成/保存时生成 thumb_url（Pillow 320px）

### 3. 废弃候选 GC
- [x] storage.delete_object
- [x] cleanup-discarded 接口 + 测试

### 4. 菜单历史版本
- [x] menu_design_versions 表 + 快照写入
- [x] GET versions + POST restore
- [x] 前端版本历史弹窗

### 5. 验证
- [x] pytest（design 35 passed）+ 前端 15 tests/build + Playwright