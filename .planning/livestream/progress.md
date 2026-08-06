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


## 2026-08-05 二.1~二.3 补齐（质量缺口）
- 二.1 persona 字段归一化（`_normalize_persona_for_engine`）：导出开播包与 engine-test 推送前，把形象风格人设（identity/tone/boundaries）映射补充引擎字段（name←identity、style←tone），保留原字段不丢信息；已是引擎格式（含 name/personality/style/knowledge_scope 任一）原样返回。新增后端测试 3 项（export 归一化 / 引擎格式透传 / engine-test 归一化）
- 二.2 开播包下载：ExportBundleModal 新增「下载引擎文件」（persona.json / wordlist.txt / script.md / reply_rules.json / engine_guide.txt）与「下载开播包」（完整 JSON，livestream-bundle-YYYY-MM-DD.json），纯 Blob 无新依赖。新增前端测试 2 项（文件名 + 内容断言，FileReader 读取 jsdom Blob）
- 二.3 最近检查展示：LiveEditorPage 基本信息引擎配置区块展示「最近健康检查」时间 + 引擎启用状态。新增前端测试 1 项
- 验证：后端 test_live.py 55 项全绿；前端 85 项全绿；typecheck / eslint / build 通过


## 2026-08-05 真实 GPU 环境推流验证（本机 RTX 4060 Laptop 8GB）
- 环境：Windows 11 + NVIDIA RTX 4060 Laptop（8GB，驱动 610.47）+ Python 3.12 venv + torch 2.6.0+cu124；Docker Desktop GPU 直通可用
- **LiveTalking（c963ad4）真实渲染 + WebRTC 推流**：
  - 模型来自 HF 镜像 hf-mirror.com `shibing624/ai-avatar-wav2lip`：wav2lip.pth（214MB）+ wav2lip_avatar_female_model（550 帧，结构 full_imgs/face_imgs/coords.pkl 与 LiveTalking 完全兼容）
  - 依赖安装：venv --system-site-packages 复用 torch；补 aiortc/aiohttp_cors/diffusers/accelerate/av 等；requirements.txt 在中文 Windows 有 GBK 解码问题 → 清洗为 ASCII 后安装
  - 启动 `python app.py --transport webrtc --model wav2lip --avatar_id wav2lip_avatar_female_model`；GPU 占用 ~6GB
  - Playwright 无头 Chromium 打开 /index.html → 填 offerAvatar → WebRTC 会话建立（SID）→ 文本驱动（edge_tts→wav2lip）→ 视频 576x768 实际播放（readyState=4, currentTime 前进）、两帧像素差 1280 万
  - 帧率日志：inferfps ≈ 43.6/47.6/50.3（远超 25）；finalfps ≈ 6.7(首段)/24.8/25.1/25.0（首段含 TTS+预热偏低，后续达标）
- **digital-human-livestream（db728c7）真实管理后台 + AiRestro engine-test 全链路**：
  - 依赖：补 flask_sockets/bilibili-api-python/azure-cognitiveservices-speech；仓库缺 `wav2lip/models/`（from wav2lip.models import Wav2Lip）→ 从 LiveTalking engines/avatars/wav2lip/models 复制补齐
  - /health → gpu_available:true, gpu_name:RTX 4060, gpu_memory_free_mb:4846
  - AiRestro engine-test（默认 + 弹幕配置两轮）全通；回读确认真实热加载：config/persona.json 改写为 L3弹幕主播、config/wordlist.txt 改写为「加微信/regex:广告\d+」，dhl 日志「人设配置已重载/敏感词词库已更新」；/admin/status persona_name 可见；/admin/render_backend 返回 wav2lip
- **实测发现并修正的契约偏差**（README 示例 vs 真实实现）：
  1. POST /admin/wordlist 真实要求 `{"content": "<每行一词文本>"}`，README 数组示例会 500 → engine-test 改为 {"content": "\n".join(wordlist)}
  2. persona 四字段（name/personality/style/knowledge_scope）必填非空 → _normalize_persona_for_engine 兜底填充
  - 已同步修正 backend engine-test、mock 引擎、后端测试、deploy README §8、livestream-api.md
- 验证脚本留档：`.planning/livestream/mock_engine.py`、`e2e_l3.py`、`engines/`（LiveTalking）、`dhl/`（digital-human-livestream）、`verify_webrtc.mjs`（Playwright，临时）、截图 frame_a/frame_b.png
- 测试：后端 test_live.py 55 项全绿（engine-test + persona 相关 18 项单独跑过）；前端 85 项不受影响

## 2026-08-05 值守人开播 SOP
- 交付 `deploy/livestream/OPERATOR-SOP.md`：面向运营/值守人（非部署工程师）的操作手册
- 内容：开播前三件套自检（AI 标识 + LiveTalking 水印 + 真人值守）、导出开播包、引擎连接测试/手动导入（wordlist 用 {"content": 文本} 格式、persona 四必填）、三条推流链路（B站 RTMP 直推 / 抖音/视频号/小红书 OBS+虚拟摄像头）、开播流程（planned→live 前置确认）、开播中互动与巡检、复盘录入 + AI 复盘、故障对照表、合规红线
- 合规终审：全文「无人直播/24小时」仅出现在「不宣传」负面表述

## 2026-08-05 形象图上传能力（用户实操反馈补齐）
- 背景：连接测试通过后实操，发现形象表单只有 image_url 手填框、无文件上传
- 后端 `POST /live-avatars/upload-image`：登录用户维度，图片 ≤10MB（PNG/JPEG/WebP，PIL 校验），MinIO `live_avatars/` 目录存储，返回 `{url: presigned(7天), object_name}`；复用 app.services.storage
- 前端 live.ts 加 uploadAvatarImage；AvatarsTab 形象图字段改为「上传按钮 + 直链输入」（Space.Compact + Upload beforeUpload → setFieldsValue image_url）
- 测试：后端 +4（成功/非图片 400/超大 400/未登录 401）→ test_live.py 59 项全绿；前端 85 项全绿；typecheck/eslint 通过
- dev 后端已重启（PID 16596）使新端点生效，.service-pids.json 已更新

## 2026-08-05 TTS 配置随开播包导出
- 背景：用户问 TTS 提供方怎么填；发现 voice_config 只存形象元数据、导出开播包未携带
- 修复：export_script 依据 script.avatar_id → live_avatars.voice_config，在 engine_guide 追加第 8 行「引擎 TTS 配置：--tts <provider> --REF_FILE <voice>」
- 默认 provider=edgetts；voice 空则只输出 --tts
- 测试：+2（cosyvoice+voice 断言 / 无配置默认 edgetts）→ test_live.py 61 项全绿

## 2026-08-05 脚本生成 502 修复（时长硬校验 → 自动缩放）
- 现象：用户生成脚本 502，detail「脚本总时长 510s 与设定时长 5 分钟偏差超过 10%」
- 根因：_clean_script 时长偏差 >10% 直接抛错；小目标（5 分钟）时 6 类分段基础时长易超
- 修复：偏差 >10% 时按比例缩放各段 duration_sec 至目标时长（保留相对权重，最长段吸收舍入差，各段 ≥1s），不再整体失败；运营仍可逐段微调
- 测试：test_script_agent_duration_deviation_rejected → autoscaled（30min/2000s → 1800s）+ 新增 small_target（5min/510s → 300s）→ test_live.py 62 项全绿
- 真实验证：duration_min=5 → 200，total_duration_sec=300（7 段）
- 另：upload-image 405 为用户浏览器端干扰（后端带登录态 multipart 实测 200）；content_main.js TypeError 为浏览器扩展注入，与项目无关

## 2026-08-05 引擎画面预览嵌入 AiRestro
- 背景：用户问「点击开播后的画面在哪看」；当前架构开播按钮只做状态流转，画面在引擎侧 webrtcapi.html
- 实现：LiveEditorPage 场次 Tab 顶部新增「引擎画面预览」Card，iframe 嵌入 {base_url}/webrtcapi.html（引擎 enabled 且有 base_url 时显示）；附说明（驱动方式 / 纯 LiveTalking 用 /index.html / 平台画面看直播伴侣）
- 测试：+1（引擎启用时场次 Tab 展示预览）→ 前端 86 项全绿；typecheck/eslint/build 通过

## 2026-08-05 引擎画面预览修正：webrtcapi.html → dashboard.html
- 背景：用户反馈预览无画面；实测发现 dhl 的 webrtcapi.html 只是 API 测试页（不建 WebRTC、video 是摆设），dhl 完整交互页是 dashboard.html
- 修正：iframe 指向 {base_url}/dashboard.html；文案说明「点开始连接 → 已连接 → 输入文本驱动」
- Playwright 实测 dashboard.html：开始连接 7s 连上，发送文本后 video 576x768 播放、两帧差 798 万像素（画面在动）
- OBS 用途：引擎 webrtc 模式可用 OBS「窗口捕获」抓 dashboard.html 画面 → 推流抖音/视频号/小红书；或引擎改 --transport virtualcam 输出虚拟摄像头由 OBS 采集

## 2026-08-05 预览框大小调节 + 画质说明
- 引擎画面预览加「预览高度」Slider（320-1100px，默认 720，适配 3:4 竖版完整显示）
- 画质提示写入预览卡：当前形象输出 576×768（3:4），画质上限由形象素材决定（更高清需 avatar.html 上传高清视频生成形象）；平台推流画质在 OBS 输出设置调整分辨率/码率
- 测试：预览测试补断言（预览高度/3:4 竖版）→ 前端 86 项全绿；typecheck/eslint/build 通过

## 2026-08-05 驱动视频上传 + TTS 提供方下拉
- 后端 POST /live-avatars/upload-video：视频 ≤200MB（MP4/WebM/MOV），MinIO live_avatars/ 存储，返回 presigned URL（7 天）+ object_name
- 前端：video_url 字段加「上传视频」按钮（Upload → uploadAvatarVideo → 回填）；provider 改 Select（TTS_OPTIONS：edgetts/cosyvoice/gpt-sovits/tencent/xtts/azuretts/doubao/fishtts/indextts2/qwentts/omnitts），voice 输入框 placeholder 随 provider 动态提示（edgetts 显示常用 Edge 音色）
- 测试：后端 +4（video 成功/非视频 400/超大 400/未登录 401）→ test_live.py 66 项全绿；前端 86 项全绿；typecheck/eslint/build 通过
- dev 后端已重启（PID 32096）生效

## 2026-08-05 主播视频一键生成引擎形象（AiRestro → LiveTalking avatar API）
- 背景：用户要求把主播图/驱动视频真正接入数字人形象生成（不只运营侧记录）
- 迁移 a1d2e3f4a5b6：live_avatars 加 engine_base_url / engine_avatar_id / engine_task_id
- 后端：
  - POST /live-avatars/{id}/engine-avatar：读形象 video_url（MinIO 下载）→ POST 引擎 /api/avatar/task（multipart video_file + model=wav2lip + avatar_id=airestro_xxx）→ 落库 engine_avatar_id/task_id
  - GET /live-avatars/{id}/engine-avatar/status：GET 引擎 /api/avatar/task/{task_id} → 返回 status/progress
- 前端：形象表单加「引擎地址」输入；列表项「生成引擎形象」按钮（校验驱动视频+引擎地址 → 创建任务 → 2s 轮询 → 进度% → completed 显示 engine_avatar_id）；列表徽标显示引擎形象 id
- 测试：后端 +6（创建成功/缺视频 400/缺引擎地址 400/引擎错误 502/status completed/idle）→ test_live.py 72 项全绿；前端 86 项全绿；typecheck/eslint/build 通过
- 迁移已应用到 dev 库（alembic upgrade head）；dev 后端重启（PID 41256）
- 前提说明：/api/avatar/task 为 LiveTalking 新版 API；当前 dhl 无该路由，生成形象需用 LiveTalking 引擎（README §7.5 已注明）

## 2026-08-05 主播视频一键生成引擎形象 · 全链路实测通过（LiveTalking）
- 引擎切换：停 dhl（无 /api/avatar/task）→ 启动 LiveTalking（engines/，c963ad4）于 8010
- 测试视频：用 wav2lip_avatar_female_model 的 550 帧合成 MP4（OpenCV，25fps，576x768，22s，5MB）
- AiRestro 实测（e2e_avatar_gen.py 留档）：
  - 上传视频（upload-video → MinIO URL）→ 建形象（video_url + engine_base_url）→ POST engine-avatar 创建任务
  - 轮询：running 20%→40%→...→ 93s **completed 100%**
  - 引擎 data/avatars 新增 **airestro_14d264977459**（550 full + 550 face + coords.pkl）
- 新形象渲染实测（Playwright）：index.html 填 offerAvatar=airestro_14d264977459 → 会话建立 8s → 视频 576x768 播放、两帧差 635 万像素
- 结论：AiRestro 上传主播视频 → 一键生成引擎形象 → 引擎 --avatar_id 渲染 全链路闭环
- 注意：当前 8010 为 LiveTalking（无 /health、/admin），AiRestro 连接测试对纯 LiveTalking 会显示健康检查失败（预期，推送标记跳过）；形象生成/渲染/RTMP 推流均可用

## 2026-08-05 形象生成 OOM 崩溃修复 + 前端并发保护
- 现象：用户生成引擎形象失败，控制台 status 502 / ERR_INSUFFICIENT_RESOURCES
- 根因（引擎日志）：多个 avatar 生成任务并发 + WebRTC 会话同时跑 → `Recovering from OOM error` → 引擎进程崩溃（RTX 4060 8GB 显存被多任务撑爆）
- 处理：
  - 重启引擎（清掉卡住的 running 任务）
  - 前端全局并发保护：一次只允许一个「生成引擎形象」任务（其它按钮禁用 + 提示等待）；生成提示「期间勿在引擎页面开直播/录制」
- 测试：前端 86 项全绿；typecheck/eslint 通过
- 建议：一次生成一个形象；视频需正面/清晰/单人；生成期间勿开引擎会话

## 2026-08-05 AI 虚拟主播形象路线（路线1：图片形象 + wav2lip 实时驱动）
- 用豆包 Seedream 5.0 生成 4 张虚拟主播形象图（2048x2048），用户选 v4
- 静态形象制作（手动，避免 s3fd 对静态图检测过慢）：
  - v4 图 → 720x960 竖版 3:4 → 300 帧静态 full_imgs
  - opencv haar 检测人脸框（204,223,509,528）→ 裁剪 face_imgs
  - coords.pkl = 300 帧相同 (y1,y2,x1,x2)
  - **坑：face_imgs 必须 256x256**（wav2lip256 模型要求；96x96 导致 conv kernel 4x4 > 输入 2x2 崩溃）
- 引擎 --avatar_id ai_avatar_v4 启动成功；Playwright 实测：会话 5s 建立，视频 currentTime 前进，两帧 5354 像素变化（嘴型实时驱动）
- 效果：静态 AI 形象 + 实时嘴型；后续可加动作编排（不说话播放轻微动作视频）
- 素材留档：.planning/livestream/ai_avatar_v{1..4}.jpg、ai_avatar_v4_static.mp4、engines/data/avatars/ai_avatar_v4/

## 2026-08-05 动作编排（路线1 增强）验证通过
- 机制：customvideo_config JSON = [{audiotype, imgpath, audiopath?}]；/set_audiotype 切换不说话时的动作画面；说话时 flush_talk 重置 audiotype=0
- 实现：
  - 基于 v4 图生成 60 帧「呼吸感」动作序列（轻微缩放 0.985~1.015 + 上下 2px + 左右 1px，2.4s 循环）→ engines/data/avatars/ai_avatar_v4_action/
  - customvideo_config.json：audiotype=2 → ./data/avatars/ai_avatar_v4_action
  - 引擎 --customvideo_config customvideo_config.json 启动
- 实测：set_audiotype(2) → code 0；动作1 vs 动作2 帧差 321 万（动作在循环）；切回 0 → 恢复主形象
- 注意：set_audiotype 的 sessionid 传 UUID 字符串（转数字会 session not found）
- 后续：可用「图生视频」生成更自然动作（微笑/点头/挥手）替换动作序列；多动作 audiotype 3/4；说话→动作自动轮换需改引擎/AiRestro 侧

## 2026-08-05 动作编排自动化（不说话自动呼吸感）
- 背景：用户反馈"不说话时没有动作和呼吸感"——之前动作配在 audiotype=2，需手动 set_audiotype 切换
- 机制：base_asr.get_audio_frame 静音时 type=1（1=silence）；process_frames 静音时按 audio_frames[0].type 找 custom_img_cycle
- 修复：customvideo_config.json 的 audiotype 由 2 改为 **1** → 静音时自动播放动作序列，无需手动切换
- 实测：连接后不手动切换，静音两帧 diff 1810 万（动作自动循环）；说话（type=0）自动走嘴型，说完自动回静音动作

## 2026-08-05 回退引擎 + AiRestro「AI 生成数字人形象」
- 回退：引擎恢复最初版本（--avatar_id wav2lip_avatar_female_model 动态形象，去掉 ai_avatar_v4 静态形象与动作编排 customvideo_config）
- 新增后端 POST /live-avatars/ai-generate-image：用户自定义描述 → 豆包 Seedream 生成 4 张 → 存 MinIO → 返回 4 个 URL
- 新增前端：形象表单「AI 生成」按钮 → 弹窗（5 个预设风格 + 自定义描述）→ 生成 4 张 grid → 点选填入形象图
- 用户自定义形象 = AI 风格描述（性别/年龄/职业/风格）+ 表单（名称/驱动类型/声音 TTS/人设）组合
- AI 视频素材：项目暂无视频生成 API，用户用可灵/即梦等生成后走既有 upload-video 上传
- 测试：后端 +4（生成成功/生图错误/缺 prompt 422/未登录 401）→ test_live.py 76 项全绿；前端 86 项全绿；typecheck/eslint/build 通过
- 实测：ai-generate-image 真实调用 75s 返回 4 张 MinIO URL

## 2026-08-05 形象图一键「同步到引擎」（预览显示新 AI 形象）
- 背景：用户反馈引擎预览还是原形象——AI 生成图只存 AiRestro 记录，引擎渲染用的是启动时 --avatar_id 的形象
- 后端 POST /live-avatars/{id}/sync-engine-static：下载形象图 → 本地生成 wav2lip 静态形象（720x960 竖版 300 帧 + face_imgs 256x256 + coords.pkl，haar 检测人脸）→ 写入引擎 data/avatars/<airestro_xxx>/ → 更新 engine_avatar_id → 自动重启引擎（--avatar_id 新形象）
- config.py 加 LIVE_ENGINE_WORKDIR / LIVE_ENGINE_VENV（本机 .env 配置；未配置则返回 400 提示）
- 前端：形象列表「同步到引擎」按钮 + 引擎形象徽标；同步后自动重启引擎并提示刷新预览
- 测试：后端 +4（成功生成/缺形象图 400/未配置目录 400/未登录 401）→ test_live.py 80 项全绿；前端 86 项全绿；typecheck/eslint/build 通过
- 实测：sync-engine-static 8s 完成，引擎自动重启用 airestro_89d1651d3365（300 帧加载 + 渲染成功）
- 用户流程：AI 生成选图保存 → 点「同步到引擎」→ 刷新预览即显示新形象

## 2026-08-05 形象库缩略图 + 动态形象同步
- 形象库：形象列表 Card 加形象图缩略图（AI 生成/上传的形象都留档可二次选用）
- 动态同步：sync-engine-static 升级——有驱动视频 → 动态形象（视频抽帧 300 帧 + 每帧 haar 人脸坐标 + face_imgs 256）；只有图 → 静态形象；返回 kind（dynamic/static）
- 前端：同步成功提示按 kind 显示「已同步动态/静态形象」
- 测试：+1 动态（20 帧视频 → dynamic 形象）→ test_live.py 81 项全绿；前端 86 项全绿；typecheck/eslint/build 通过
- 实测：动态 sync 21s，引擎重启用 airestro_01d785f958aa（300 帧）；不说话两帧 diff 2343 万（身体在动）、说话嘴型正常
- 动态素材来源：用户可用可灵/即梦「图生视频」生成动态视频 → 上传驱动视频 → 同步即得动态形象

## 2026-08-05 「生成引擎形象」稳化：视频达标检查 + 预处理 + 生成后自动重启
- 背景：用户反馈「同步到引擎」效果差（静态不动/动态扭曲），想走引擎 s3fd 官方流程（生成引擎形象），但卡 40%
- 实现：
  - _prepare_engine_video：提交前达标检查（≥6秒/150帧、平均亮度≥45、haar 正脸检出率≥50%）→ 不达标返回 400 明确原因（不再让引擎卡 40%）；达标则转 720x960 竖版 + gamma 提亮后提交引擎
  - create_engine_avatar：下载视频 → _prepare_engine_video → 提交 /api/avatar/task（预处理后的视频）
  - get_engine_avatar_status：completed → 自动 _restart_live_engine 用新形象（幂等：已在用则跳过）
  - _restart_live_engine 幂等：当前引擎 cmdline 已含该 avatar_id 则跳过重启
  - 前端「生成引擎形象」按钮加 Tooltip（需达标视频说明）
- 测试：+3（不达标视频 400 / 短视频拒绝单元 / completed 自动重启断言）→ test_live.py 83 项全绿；前端 86 项全绿
- 说明：用户用 AI 生成达标视频（正面/单人/≥6秒/光线足）→ 生成引擎形象 → 引擎 s3fd 高质量动态形象 → 自动重启引擎切换

## 2026-08-05 引擎 GPU 生命周期管理（自动释放）
- 背景：用户 GPU 常被引擎占满（~6GB），要求生成失败/结束直播自动释放
- 实现：
  - _release_live_engine()：停止本机引擎进程释放 GPU
  - POST /live-engines/release、/live-engines/start：手动释放/启动
  - 场次 live→ended 自动 _release_live_engine（结束直播释放 GPU）
  - engine-avatar status failed → 自动重启引擎清理卡死任务显存
- 前端：场次 Tab 预览卡加「释放 GPU」「启动引擎」按钮
- 测试：+3（release 端点/start 端点/live→ended 自动释放）→ test_live.py 86 项全绿；前端 86 项全绿
- 实测：释放前 7.7GB/100% → release → 1.4GB/25%（释放 6.3GB），8010 停止
- 引擎当前已停止（GPU 释放）；需用时点「启动引擎」（~30s 就绪）

## 2026-08-05 驱动视频达标检查优化（先预处理再检查）
- 背景：用户视频 245s/39亮度/44%正脸检出，原始检查两项不达标被 400
- 优化：_prepare_engine_video 改为「先转 720x960 竖版 + gamma 1.2 提亮 → 再对预处理后帧检查」——竖版中心裁剪放大脸、提亮提亮度，检查的就是实际喂引擎的画面
- 实测：用户视频通过（预处理后 3.6MB，6s）；后端 8 项相关测试全绿
- 说明：预处理先做再检查，能救回"轻微偏暗/脸略小"的视频；真正无脸/极暗仍会 400 明确提示

## 2026-08-06 修复：释放 GPU 报错（_release_live_engine 被误删）
- 现象：点「释放 GPU」500 不成功
- 根因1：重写 _prepare_engine_video 时替换边界覆盖删掉了 _release_live_engine 函数 → 端点 NameError 500
- 根因2：8000 端口被旧后端进程（19224，加载旧代码）占用，新进程启动失败
- 修复：恢复 _release_live_engine；清理旧进程重启新后端（PID 32968）
- 验证：release 端点实测 200 {released:true}；TestClient 200；相关测试通过

## 2026-08-06 「生成引擎形象」失败修复：引擎不在线自动拉起
- 现象：引擎被释放后未启动，点生成引擎形象失败（后端无法连引擎）
- 修复：create_engine_avatar 提交任务前 _ensure_engine_online（探测失败 → 自动 _restart_live_engine 启动 + 轮询等待就绪 ≤90s；仍失败才 502 明确提示）
- 测试：+2（不在线自动启动/在线不重启，整模块替换 httpx mock）→ test_live.py 88 项全绿
- 另：过程中发现 Postgres 容器掉线导致测试 ERROR，已 docker start 恢复

## 2026-08-06 生成后自动切换改为后端后台监控（不依赖前端轮询）
- 现象：生成引擎形象中途登出 → 轮询断 → 任务实际 completed（airestro_6b2b483f17e0，450 帧动态）但引擎没切新形象；GPU 生成中占满
- 修复：
  - _watch_engine_avatar_task 后台协程：create_engine_avatar 提交成功后 asyncio.create_task 后台每 5s 查引擎任务，completed → _restart_live_engine(新形象)；failed → 清理。前端登出/关页不影响
  - 已手动把引擎切到 airestro_6b2b483f17e0（450 帧加载完成上线）
- 测试：+1（后台监控 completed 自动重启）→ test_live.py 89 项全绿
- 遗留：中途登出根因待观察（前端 401 拦截器 remove token 跳登录），若复现再查 auth

## 2026-08-06 修复：新形象未应用成功（8010 被旧引擎占用）
- 现象：引擎侧进程参数显示新形象，但用户预览仍是旧形象（金发女模特 576x768）
- 根因：_restart_live_engine 杀进程后立即启动新进程，旧进程未完全退出/端口未释放 → 新进程启动失败退出；8010 实际仍被旧引擎（wav2lip_avatar_female_model）监听；此前查进程用 First 1 误取到失败的"新进程"
- 修复：_restart_live_engine 杀进程后等待端口 8010 释放（_port_in_use 探测，最多 15s）再启动
- 手动彻底清理旧引擎进程（14172/20692），用新形象 airestro_6b2b483f17e0 启动；netstat 确认 8010 监听 PID 15496 = 新形象引擎
- 最终验证：index.html 渲染 720x960（新形象分辨率）播放中
- 用户操作：强制刷新前端（Ctrl+Shift+R）→ 预览点开始连接即见新形象
