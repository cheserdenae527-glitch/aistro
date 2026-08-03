# D2 — 视觉设计前端实时图片编辑器（task plan）

> 来源：docs/PLAN-DESIGN.md（D2）+ docs/SPEC-DESIGN.md v0.1 + docs/contracts/design-api.md
> 目标：上传/AI 生成图进入统一编辑器，所有操作实时预览；保存成品到 MinIO；429/422 提示。

## 阶段

### 1. 基础设施
- [x] 路由 /design + /design/:id，侧边栏入口
- [x] designService（真实 API 联调，非 mock）
- [x] 抽取复用 CropModal

### 2. 项目列表 + 新建
- [x] DesignIndexPage：按门店分组项目、新建项目

### 3. 素材库面板
- [x] 上传 / AI 生成 Drawer（4 候选 → confirm）/ 素材列表 / 删除 409

### 4. 编辑器
- [x] CanvasPreview 实时预览
- [x] Toolbar：裁剪/旋转/滤镜/文字/背景替换/增强
- [x] PropertyPanel：亮度/对比度/饱和度/色温滑块 + 滤镜 + 文字
- [x] bg-replace/enhance → 4 候选 → confirm → 替换画布源图
- [x] 一键美化 → Pillow API → 结果进入编辑器
- [x] 撤销/重做 + 保存 canvas.toDataURL → /save

### 5. 测试
- [x] Vitest：edit_stack 撤销/重做、滑块参数序列化

### 6. 联调验证
- [x] Swagger 反查契约一致性（13/13 覆盖）
- [x] 前端 build 通过
- [x] 视觉一致性检查路径（Pillow 对照载入）

## 已知妥协
- 文字标签 MVP 用 DOM 叠加预览，保存时画布统一绘制。
- 裁剪输出尺寸沿用素材自然尺寸。
