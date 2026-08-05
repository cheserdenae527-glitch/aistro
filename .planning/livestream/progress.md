# Livestream L2 Progress

## 2026-08-05 L2 完成
- services/live.ts：全量类型 + liveService（项目/形象/脚本/弹幕/合规/场次/复盘）
- utils/live.ts：平台/状态/分段标签 + formatDuration/activeScript/shouldConfirmRegenerate/canExport 等 helper + 7 项单测
- 组件 components/live/：
  - AvatarsTab：形象库（org 共享）列表/新建/编辑/删除 + 声音/人设表单
  - ScriptTab：生成（二次确认归档）、批次选择、分段微调保存、合规自检、定稿（pass=false 禁用）、导出开播包（归档禁用）
  - DanmakuTab：AI 生成 + 编辑回复规则/敏感词/转人工话题 + 旧脚本版本提示
  - SessionsTab：场次列表 + 开播前置确认弹窗（值守人+AI 标识）、补录（必填时间）、编辑/取消/删除/备注、复盘数据录入 + AI 复盘
  - ExportBundleModal：脚本/persona/wordlist/回复规则/合规清单/引擎说明 + 复制
- 页面：LiveIndexPage（商家→门店→项目分组 + 新建）、LiveEditorPage（五 Tab + 基本信息：平台/目标/AI 标识/优惠商品/引擎配置）
- 路由/侧边栏：App.tsx 新增 /live + /live/:id +「直播工坊」入口
- 前端测试：utils/live.test.ts 7 项 + LiveEditorPage.test.tsx 6 项（定稿/导出禁用、regenerate 二次确认、开播前置校验、补录必填）全绿；全套 78 项通过
- 质量：typecheck / eslint / production build 全过；dev 后端 + vite 代理连通（/live 200，/api/v1/live-projects 401 正常）
- 注：antd 双汉字按钮自动插空格（定 稿/补 录），测试用 /定\s*稿/ 匹配；validateFields 校验失败已 try/catch 防未处理 rejection


## 2026-08-05 L3 完成（本地引擎接入）
- 核实两仓库最新部署方式（固定验证 commit）：
  - lipku/LiveTalking `c963ad4`：Ubuntu 22.04 / Py3.12 / PyTorch 2.9.1 / CUDA 12.8；wav2lip256（3060=60fps / 3080Ti=120fps）、musetalk（3080Ti+）；TCP:8010 + UDP 1-65536；RTMP/WebRTC/虚拟摄像头；README §7 要求 B站/视频号/抖音带水印与标识
  - l11223/digital-human-livestream `db728c7`：Py3.10+ / CUDA 11.6+；persona.json + wordlist.txt（regex: 前缀）热加载；管理后台 API（/health、/admin/persona、/admin/wordlist、/admin/livestream/start|stop、/admin/render_backend）；Docker --gpus all --network=host
- 交付物：
  - `deploy/livestream/README.md`：两种部署路径 + Windows/Ubuntu + GPU 要求 + RTMP/WebRTC/虚拟摄像头(OBS) + 水印/AI 标识提醒 + 管理后台 API 速查 + Docker + FAQ + 平台规则以最新公告为准
  - `docs/contracts/livestream-bundle.schema.json`：draft-2020-12，六字段全定义，persona 对齐 digital-human-livestream config/persona.json，wordlist 支持 regex: 前缀；样例开播包 jsonschema 校验通过
  - 后端 `POST /live-projects/{id}/engine-test`：base_url 覆盖/健康检查(15s)/persona+wordlist 推送（404→skipped 不阻断、其余失败 502）；通过后写回 engine_config.last_health_check；GET 保持 api_key 脱敏；override 地址不污染项目配置
  - 前端「基本信息」Tab「连接测试」按钮：Form.useWatch 响应式启用、展示健康检查/人设/敏感词推送结果、最近检查时间；失败走 showApiError
  - 契约文档 livestream-api.md 增补 engine-test 端点 + 安全表
- 测试：
  - 后端 tests/test_live.py 52 项全绿（新增 12 项 engine-test：健康/推送/脱敏/400/502/skipped/danmaku 优先级/覆盖/跳过）
  - 前端 82 项全绿（新增 4 项连接测试）+ typecheck/eslint/build 通过
  - 修复测试隔离：test_live.py 增加每测试重置登录频控的 autouse fixture（整套 900s 窗口累计登录触发 429 的确定性失败）
- 端到端验证（无 GPU，mock 引擎 `mock_engine.py` :8010 + 临时后端 :8011）：
  - engine-test 默认推送：健康检查 200（5ms）+ 占位人设 + 内置词库 → mock 落库；last_health_check 写回；GET 脱敏
  - 配置弹幕 persona + wordlist 后再次 engine-test → mock 回读确认热加载（name=L3弹幕主播 / ["加微信","regex:广告\\d+"]）
  - 覆盖 base_url（不可达）→ 502 且不污染项目 engine_config
  - 开播包 JSON Schema 校验通过；cleanup 删除测试项目
  - 脚本：`.planning/livestream/mock_engine.py`、`.planning/livestream/e2e_l3.py`（本地留档，不入库）
- 合规终审：deploy/docs 全文检索「无人直播/24小时无人直播」仅出现在「不宣传」负面合规表述；`_build_engine_guide` 已含 LiveTalking 水印提醒 + AI 标识文案（test_live.py:823 断言 "LiveTalking" in engine_guide）
