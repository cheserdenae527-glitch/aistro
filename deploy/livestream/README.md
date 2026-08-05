# 直播工坊 · 本地引擎部署指南（L3）

> 版本：v1.0 · 2026-08-05（L3 交付）
> 依据：docs/PLAN-LIVESTREAM.md L3 / docs/SPEC-LIVESTREAM.md §3.1
> 适用：把 AiRestro 导出的「开播包」（script_markdown / persona_json / wordlist / reply_rules / compliance / engine_guide）落地到本地数字人引擎并推流。
> **值守人操作手册见 [`OPERATOR-SOP.md`](./OPERATOR-SOP.md)**（导出→导入→推流→开播→复盘 检查清单）；本文档面向部署工程师。
> 边界：AiRestro 只生产草稿与配置，不直接发布、不直接推流；数字人引擎在本机 / 私有 GPU 环境部署（Apache-2.0 开源），开播前由真人运营确认（值守 + AI 标识）。

## 0. 一句话路线

```
AiRestro 导出开播包
  → 本地部署数字人引擎（LiveTalking 或 digital-human-livestream）
  → 导入 persona.json / wordlist.txt（管理后台 API 热加载）
  → 启动数字人渲染（WebRTC / RTMP / 虚拟摄像头）
  → 真人值守开播（平台直播伴侣 / OBS 推流）
```

## 1. 引擎选型

| 引擎 | 仓库 | 适用 | 说明 |
|---|---|---|---|
| **LiveTalking** | [lipku/LiveTalking](https://github.com/lipku/LiveTalking)（Apache-2.0） | 纯数字人推流 | 数字人视频实时生成 + WebRTC/RTMP/虚拟摄像头输出，`/human` API 文本驱动 |
| **digital-human-livestream** | [l11223/digital-human-livestream](https://github.com/l11223/digital-human-livestream)（Apache-2.0） | 带管理后台 + 弹幕互动 | 基于 LiveTalking 二次开发：B站弹幕采集 + DeepSeek 对话 + 人设/敏感词热加载 + Web 管理后台 + Docker |

- 两个仓库迭代较快，本文档**固定以 2026-08-05 核实的 commit 为准**：
  - LiveTalking：`c963ad409c556918b7d23999bf87c47a7c05c932`
  - digital-human-livestream：`db728c7cf3ac202d9fc2099a7ff10464f7b27ff8`
- 在线中文文档：<https://doc.livetalking.ai>（含 FAQ / AutoDL / UCloud 教程 / RTMP / 虚拟摄像头 / API 章节）。

## 2. 硬件与系统要求（GPU）

| 项 | 最低要求 | 说明 |
|---|---|---|
| 系统 | Ubuntu 22.04（推荐）/ Windows 10/11（整合包或 WSL2） | LiveTalking 官方测试环境：Ubuntu 22.04 + Python 3.12 + PyTorch 2.9.1 + CUDA 12.8 |
| GPU（wav2lip） | **RTX 3060 及以上**（8GB+ 显存） | wav2lip256：3060≈60fps、3080Ti≈120fps |
| GPU（musetalk） | **RTX 3080Ti 及以上** | musetalk：3080Ti≈42fps、3090≈45fps、4090≈72fps |
| 实时判定 | 后端日志 `inferfps`（GPU 推理帧率）与 `finalfps`（最终推流帧率）**均需 ≥25** | 低于 25 视为不实时，需降分辨率 / 换模型 / 升显卡 |
| 端口 | TCP:8010 + UDP 1-65536（WebRTC） | 远程部署需在云安全组放通；AutoDL 无法开放 UDP，需自建 SRS 或 TURN 转发 |
| 内存/CPU | 16GB+ RAM；多路并发时 CPU 用于视频压缩 | 不说话时并发取决于 CPU，同时说话并发取决于 GPU |

> 无本地 GPU：可用云 GPU（Compshare/UCloud 镜像、AutoDL 等）。AiRestro 侧无 GPU 也能完成「导出开播包 + 健康检查 + 配置导入」验证，推流验证需在有 GPU 的机器上执行。

## 3. 部署路径 A：LiveTalking（纯推流，Ubuntu 22.04）

### 3.1 安装依赖

```bash
git clone https://github.com/lipku/LiveTalking.git
cd LiveTalking
git checkout c963ad409c556918b7d23999bf87c47a7c05c932   # 固定验证版本

conda create -n livetalking python=3.12
conda activate livetalking

# CUDA 版本非 12.8 时，按 PyTorch 官网 previous-versions 安装对应版本
pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 \
  --index-url https://download.pytorch.org/whl/cu128

pip install -r requirements.txt
```

### 3.2 下载模型（网盘：夸克 / Google Drive，见仓库 README §2.1）

```text
wav2lip256.pth           → 拷贝到 models/ 并重命名为 wav2lip.pth
wav2lip256_avatar1.tar.gz → 解压后整个文件夹放入 data/avatars/
```

### 3.3 启动

```bash
python app.py --transport webrtc --model wav2lip --avatar_id wav2lip256_avatar1
```

- 服务端需开放 **TCP:8010 + UDP:1-65536**
- 客户端验证：浏览器打开 `http://服务器IP:8010/index.html`，点「开始连接」，文本框输入文字提交即可驱动数字人
- 管理页：`/avatar.html`（上传视频生成形象）、`/admin.html`（会话监控与全局配置）

### 3.4 输出方式

| 输出 | 用法 | 适用 |
|---|---|---|
| WebRTC | 浏览器 `/index.html` 直接播放 | 本机调试 / 大屏 |
| RTMP | 数字人视频以 RTMP 推流（B站/YouTube 等提供 RTMP 地址的平台可直接推） | 直播平台推流 |
| 虚拟摄像头 | 输出为系统摄像头设备，OBS 捕获后再由 OBS 推流到任意平台 | 抖音 / 视频号 / 小红书等需直播伴侣或 OBS 的平台 |

### 3.5 动作编排与 TTS

- 动作编排：不说话时可播放自定义视频，配合带货讲解更自然
- TTS：EdgeTTS / GPT-SoVITS / CosyVoice / 腾讯云等多方案，按 `registry.py` 插件机制扩展
- 数字人模型：ernerf / musetalk / wav2lip / Ultralight

## 4. 部署路径 B：digital-human-livestream（管理后台 + B站弹幕互动）

> 与 AiRestro 开播包字段（persona_json / wordlist）**直接对齐**，推荐优先使用：管理后台 API（`/health`、`/admin/persona`、`/admin/wordlist`）支持热加载，可被 AiRestro「连接测试」直接调用。

### 4.1 安装（Python 3.10+ / CUDA 11.6+）

```bash
git clone https://github.com/l11223/digital-human-livestream.git
cd digital-human-livestream
git checkout db728c7cf3ac202d9fc2099a7ff10464f7b27ff8   # 固定验证版本

conda create -n livetalking python=3.10
conda activate livetalking
conda install pytorch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 pytorch-cuda=12.4 -c pytorch -c nvidia
pip install -r requirements.txt
```

### 4.2 环境变量

| 变量 | 说明 | 默认 | 必填 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — | ✅ |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com` | |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` | |
| `BILIBILI_ROOM_ID` | B站直播间 ID（弹幕互动） | — | |
| `PERSONA_CONFIG_PATH` | 人设配置路径 | `config/persona.json` | |
| `WORDLIST_PATH` | 敏感词词库路径 | `config/wordlist.txt` | |

### 4.3 人设与敏感词（与 AiRestro 开播包对齐）

`config/persona.json`：

```json
{
  "name": "店长小雅",
  "personality": "亲切热情，懂美食",
  "style": "烟火气，口语化",
  "knowledge_scope": "本店菜品、优惠、营业信息",
  "forbidden_topics": ["政治", "宗教"]
}
```

`config/wordlist.txt`（每行一个词；`regex:` 前缀为正则）：

```text
敏感词1
敏感词2
regex:广告\d+
regex:加微信.*\d{6,}
```

- 输入过滤：弹幕进入 LLM 前检查；输出过滤：LLM 回复发出前检查；双向过滤
- 支持热加载：通过管理后台实时更新，无需重启

### 4.4 启动

```bash
python app.py --transport webrtc --model wav2lip --avatar_id wav2lip256_avatar1 \
  --persona_config config/persona.json \
  --room_id <B站直播间ID> \
  --wordlist config/wordlist.txt
```

- 数字人互动页面：`http://服务器IP:8010/webrtcapi.html`
- 管理后台：`http://服务器IP:8010/admin.html`
- 切换 MuseTalk 渲染：`--model musetalk --avatar_id <你的形象>`

### 4.5 Docker 部署

```bash
docker build -t digital-human-live -f Dockerfile .
docker run --gpus all -it --network=host \
  -e DEEPSEEK_API_KEY="your-key" \
  -e DEEPSEEK_BASE_URL="https://api.deepseek.com" \
  digital-human-live
```

> 云 GPU（推荐 AutoDL）：选 CUDA 12.x + Python 3.10 镜像 → 克隆项目装依赖 → 配环境变量 → 启动并开放 8010 端口。

## 5. Windows 部署

| 方式 | 说明 | 适用 |
|---|---|---|
| **官方 Windows 整合包** | LiveTalking 提供整合包（见仓库 README §2.5），解压即用，含 Python/依赖/模型 | 无 Linux 经验、本机有 NVIDIA GPU |
| **WSL2 + Ubuntu 22.04** | 在 WSL2 内按 §3/§4 的 Ubuntu 步骤执行；注意 WSL2 的 GPU 透传需 Windows 侧安装匹配的 NVIDIA 驱动 | 已有 WSL2 环境 |
| **conda 原生 Windows** | Python 3.10/3.12 + 对应 CUDA 版 PyTorch 安装，命令同 §3.1/§4.1 | 熟悉 conda |

> 虚拟摄像头在 Windows 上需额外安装虚拟摄像头驱动（如 OBS Virtual Camera），供直播伴侣/OBS 采集。

## 6. 输出与推流配置

### 6.1 WebRTC（调试优先）

```bash
python app.py --transport webrtc --model wav2lip --avatar_id wav2lip256_avatar1
# 浏览器打开 http://localhost:8010/index.html
```

### 6.2 RTMP 直推（平台提供 RTMP 地址时）

- LiveTalking 支持 RTMP 输出；B站/YouTube 等平台可在开播设置里拿到 RTMP 推流地址与串流密钥
- 将推流地址填入引擎输出配置即可直推；抖音/视频号/小红书多数情况下走「直播伴侣」而非公开 RTMP，见 6.4

### 6.3 虚拟摄像头（OBS 链路，通用方案）

```text
LiveTalking（虚拟摄像头输出）→ OBS 采集摄像头源 → OBS 推流（任意平台 RTMP/直播伴侣）
```

1. 引擎启动后选择「虚拟摄像头」输出
2. OBS 添加「视频采集设备」→ 选择该虚拟摄像头
3. OBS 推流到目标平台（抖音直播伴侣 / 视频号助手 / 小红书直播等）

### 6.4 抖音 / 视频号 / 小红书实测要点

- 抖音：用「抖音直播伴侣」→ 添加摄像头源（选虚拟摄像头），不要直接在直播伴侣里重复渲染
- 视频号：视频号助手开播后选择「OBS 虚拟摄像头」作为画面源
- 小红书：小红书直播伴侣同理会话摄像头源
- 以上平台规则与开播流程会随版本变化，**以平台最新公告 / 直播伴侣实际选项为准**（AiRestro 导出包 engine_guide 已附同款提醒）

## 7. 开播包导入（AiRestro → 引擎）

1. AiRestro 直播脚本 Tab → [导出开播包]（仅当前活跃批次的定稿脚本可导出）
2. 开播包字段与引擎配置对应：

| 开播包字段 | 引擎落点 |
|---|---|
| `persona_json` | digital-human-livestream `config/persona.json` / `POST /admin/persona` |
| `wordlist` | `config/wordlist.txt` / `POST /admin/wordlist`（每行一词，`regex:` 前缀为正则） |
| `script_markdown` | 直播脚本文本，供值守人对照执行 / 粘贴到引擎文本驱动 |
| `reply_rules` | 候选话术；平台不在 MVP 自动弹幕范围时由值守人人工粘贴 |
| `engine_guide` | 启动命令 + RTMP 地址 + 水印/AI 标识提醒 |

3. 引擎侧验证：`GET /health` → `POST /admin/persona`（人设）→ `POST /admin/wordlist`（敏感词）→ 管理后台 `GET /admin/persona`、`GET /admin/wordlist` 回读确认热加载生效
4. AiRestro 侧：项目基本信息 Tab → 填写引擎管理后台地址 → [连接测试] 一键完成「健康检查 + 配置推送」，通过后 `engine_config.last_health_check` 自动更新

## 7.5 形象生成（AiRestro → 引擎，一键出形象）

- AiRestro 数字人形象 → 「生成引擎形象」按钮：把该形象的**驱动视频**提交到引擎
  `POST /api/avatar/task`（LiveTalking Avatar 生成 API）→ 轮询
  `GET /api/avatar/task/{task_id}` → 完成后引擎侧生成 `data/avatars/<airestro_xxx>/`
- 之后引擎用 `--avatar_id <airestro_xxx>` 启动即可使用该形象（正面、光线均匀、少遮挡、1-2 分钟视频最佳）
- **前提**：引擎需支持 `/api/avatar/task`（LiveTalking 新版含此 API；当前 digital-human-livestream db728c7 未裁剪该路由，如需生成形象请用 LiveTalking 引擎或后续给 dhl 补路由）

## 8. 管理后台 API 速查（engine-test 对接）

> digital-human-livestream 管理后台 API；响应格式：成功 `{"code":0,"data":{...}}`，失败 `{"code":-1,"msg":"..."}`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/admin/status` | 系统状态（直播/弹幕队列/LLM） |
| GET/POST | `/admin/persona` | 获取 / 更新人设（JSON body：name/personality/style/knowledge_scope/forbidden_topics） |
| GET/POST | `/admin/wordlist` | 获取 / 更新敏感词 |
| POST | `/admin/livestream/start` / `/admin/livestream/stop` | 开始 / 停止直播 |
| GET/POST | `/admin/render_backend` | 获取 / 切换渲染后端（wav2lip / musetalk） |

```bash
curl http://localhost:8010/health
curl -X POST http://localhost:8010/admin/persona \
  -H "Content-Type: application/json" \
  -d '{"name":"店长小雅","personality":"亲切热情","style":"烟火气","knowledge_scope":"本店菜品","forbidden_topics":["政治","宗教"]}'
curl -X POST http://localhost:8010/admin/wordlist \
  -H "Content-Type: application/json" \
  -d '{"content":"加微信\nregex:广告\\d+"}'
```

> **以真实实现为准（2026-08-05 实测）**：仓库 README 的 wordlist 示例是 JSON 数组，但实际代码（`admin.py`）要求
> `{"content": "<每行一词的文本>"}`；persona 四字段（name/personality/style/knowledge_scope）**必填且非空**，
> 否则返回 `{"code":-1,"msg":"配置缺少必需字段..."}`。AiRestro engine-test 已按真实格式推送。

## 9. 合规提醒（必读）

1. **LiveTalking 水印/标识**：LiveTalking 开源声明（README §7）要求发布到 B站 / 视频号 / 抖音的视频**必须带 LiveTalking 水印与标识**；与 AiRestro 的 AI 标识合规要求方向一致，导出开播包 `engine_guide` 已保留该提醒，开播前确认水印/标识已叠加。
2. **AI 标识 + 真人值守**：依据《直播电商监督管理办法》与《人工智能拟人化互动服务管理暂行办法》，数字人直播需 AI 标识 + 真人值守。AiRestro 在 planned→live 时强制校验 `duty_confirmed`（值守人）+ `ai_label_confirmed`。
3. **不宣传「无人直播」**：本模块与本文档不宣传、不出现「无人直播 / 24 小时无人直播」等表述；AiRestro 敏感词词库已内置红线话术（含「无人直播」）并在脚本/人设/导出内容中拦截。
4. **平台规则动态变化**：抖音/视频号/小红书对数字人直播的要求会更新，一律**以平台最新公告为准**。
5. **站外交易引导**：不引导微信转账等站外私下交易；`wordlist` 内置站外交易引导词。

## 10. 常见问题

| 问题 | 处理 |
|---|---|
| 画面不实时 / 帧率低 | 看后端日志 `inferfps` / `finalfps`，≥25 才实时；降低分辨率、换 wav2lip、升显卡 |
| WebRTC 连不上 | 检查 TCP:8010 与 UDP 端口放通；AutoDL 无法开放 UDP → 自建 SRS 或 TURN |
| 模型下载慢 | 用夸克网盘 / Google Drive 下载后按 §3.2 放置；确认目录名与 avatar_id 一致 |
| 管理后台 POST 返回 `{"code":-1}` | 按 `msg` 修正请求体；persona 字段名、wordlist 格式须与 §4.3 对齐 |
| 弹幕不采集 | 确认 `--room_id` 为 B站直播间 ID、网络可达、直播已开始；`POST /admin/livestream/start` 后再观察 |

## 附：L3 验证记录（2026-08-05）

**第一阶段 · mock 引擎（无 GPU 语义验证）**
- 本地起一个实现 `/health` + `/admin/persona` + `/admin/wordlist` 的 Python 服务完成端到端验证：
  - AiRestro `POST /live-projects/{id}/engine-test` → 健康检查 200 + persona/wordlist 推送成功
  - 回读 `/admin/persona`、`/admin/wordlist` 确认热加载生效；`engine_config.last_health_check` 落库

**第二阶段 · 真实 GPU 环境（本机 RTX 4060 Laptop 8GB，Windows 11）**
- **LiveTalking（c963ad4）真实渲染 + WebRTC 推流**：
  - 模型：`shibing624/ai-avatar-wav2lip`（HF 镜像 hf-mirror.com）的 `wav2lip.pth`（214MB）+ `wav2lip_avatar_female_model` 形象（550 帧）
  - Python 3.12 venv + torch 2.6.0+cu124；`python app.py --transport webrtc --model wav2lip --avatar_id wav2lip_avatar_female_model`
  - 无头 Chromium（Playwright）打开 `/index.html` → WebRTC 会话建立 → 文本驱动（edge_tts → wav2lip）→ 视频 576×768 实际播放、两帧像素差 1280 万（画面在动）
  - 帧率：`inferfps ≈ 44–50`（远超 25 实时阈值）；`finalfps ≈ 25`（首段含 TTS+预热略低 6.7，后续达标）
- **digital-human-livestream（db728c7）真实管理后台 + AiRestro engine-test 全链路**：
  - `/health` → `{"code":0,"data":{"status":"ok","gpu_available":true,"gpu_name":"NVIDIA GeForce RTX 4060 Laptop GPU","gpu_memory_free_mb":4846}}`
  - AiRestro engine-test（默认 + 弹幕配置两轮）→ persona/wordlist 推送成功；回读确认**真实热加载**：`config/persona.json` 被改写为 L3弹幕主播、`config/wordlist.txt` 被改写为「加微信 / regex:广告\d+」，dhl 日志「人设配置已重载 / 敏感词词库已更新」
  - `/admin/status` 显示 `persona_name: L3弹幕主播`；`/admin/render_backend` 返回 `wav2lip`
  - 实测发现并修正：wordlist 推送需 `{"content": 文本}`（README 数组示例与实际实现不符）、persona 四字段必填非空 → 已同步修正 AiRestro engine-test 与本文档
- **Docker GPU 直通**：`docker run --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi` 容器内可见 RTX 4060（本机 Docker 可直通 GPU）
- 详细记录见 `.planning/livestream/progress.md`。
