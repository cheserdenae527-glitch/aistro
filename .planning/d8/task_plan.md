# D8 — S2 内容工坊前端（task plan）

## 步骤

### 1. 路由与入口
- [x] /studio + /studio/:id 路由 + 侧边栏「内容工坊」

### 2. 服务层
- [x] frontend/src/services/studio.ts（类型 + API 封装，含 multipart 上传）
- [x] frontend/src/utils/studio.ts（校验 / QA 汇总 / 主题常量 / 选择器）

### 3. 页面
- [x] StudioIndexPage 项目列表 + 新建（选门店）
- [x] StudioEditorPage 三步流程：文案（表单+生成+429 倒计时+5 标题+正文+标签+保存）→ 卡组（模板/色板/页数/素材/生成+预览+QA）→ 导出
- [x] AssetPickerDrawer（素材库引用 + 直接上传，总数 ≤8）

### 4. 后端配合
- [x] multipart 卡组接口支持 asset_ids（素材库+上传可同时用）+ 测试

### 5. 验证
- [x] Vitest 21 个新用例（表单校验/页数限制/素材选择/QA）
- [x] lint / typecheck / build 全绿
- [x] 真实 API 冒烟（DeepSeek + Playwright 渲染 4 页 QA 全过）
- [x] Playwright UI 冒烟（登录→列表→编辑器 Step2 预览→Step3 导出）
